"""
Shared Message Bus for real-time agent communication.
Bridges AutoGen agent messages to WebSocket clients and CLI output.
"""

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import List, Callable, Optional
from datetime import datetime
import backend.projects_db as db


@dataclass
class AgentMessage:
    """Represents a single message from an agent."""
    agent_name: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message_type: str = "agent"  # agent, system, error, status

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_type": self.message_type
        }


class MessageBus:
    """
    Central message bus for the multi-agent system.
    Supports both async (WebSocket) and sync (CLI) consumers.
    """

    def __init__(self):
        self._history: List[AgentMessage] = []
        self._async_queues: List[asyncio.Queue] = []
        self._sync_callbacks: List[Callable] = []
        self._task_status: str = "idle"  # idle, running, complete, error
        self._current_task: Optional[str] = None
        self.active_project_id: Optional[str] = None

    @property
    def history(self) -> List[AgentMessage]:
        return self._history.copy()

    @property
    def task_status(self) -> str:
        return self._task_status

    @property
    def current_task(self) -> Optional[str]:
        return self._current_task

    def set_task_status(self, status: str, task: Optional[str] = None):
        """Update task status and optionally the task description."""
        self._task_status = status
        if task is not None:
            self._current_task = task
        # Broadcast status change
        self.publish(AgentMessage(
            agent_name="System",
            content=f"Task status: {status}" + (f" — {task}" if task else ""),
            message_type="status"
        ))

    def publish(self, message: AgentMessage):
        """Publish a message to all subscribers."""
        self._history.append(message)
        
        # Save to persistent storage if a project is active
        if self.active_project_id and message.message_type != "status":
            try:
                db.save_message(self.active_project_id, message.to_dict())
            except Exception as e:
                print(f"Error saving message to project: {e}")

        # Notify async subscribers (WebSocket)
        for queue in self._async_queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass  # Drop message if queue is full

        # Notify sync subscribers (CLI)
        for callback in self._sync_callbacks:
            try:
                callback(message)
            except Exception as e:
                print(f"Error in message callback: {e}")

    def subscribe_async(self) -> asyncio.Queue:
        """Create a new async subscription (for WebSocket clients)."""
        queue = asyncio.Queue(maxsize=1000)
        self._async_queues.append(queue)
        return queue

    def unsubscribe_async(self, queue: asyncio.Queue):
        """Remove an async subscription."""
        if queue in self._async_queues:
            self._async_queues.remove(queue)

    def subscribe_sync(self, callback: Callable):
        """Register a sync callback (for CLI output)."""
        self._sync_callbacks.append(callback)

    def unsubscribe_sync(self, callback: Callable):
        """Remove a sync callback."""
        if callback in self._sync_callbacks:
            self._sync_callbacks.remove(callback)

    def clear_history(self):
        """Clear message history."""
        self._history.clear()
        if self.active_project_id:
            db.clear_history(self.active_project_id)

    def set_active_project(self, project_id: str):
        """Switch the active project and load its history."""
        self.active_project_id = project_id
        self._history.clear()
        
        project_data = db.get_project(project_id)
        if project_data and "messages" in project_data:
            for msg_dict in project_data["messages"]:
                try:
                    msg = AgentMessage(**msg_dict)
                    self._history.append(msg)
                except Exception:
                    pass

# Global singleton message bus
message_bus = MessageBus()
