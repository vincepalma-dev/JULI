"""
Thread-safe message bus for agent events.

Agents publish from worker threads; WebSocket consumers read asyncio queues on
the event loop. publish() hands each message to a queue's own loop with
loop.call_soon_threadsafe and drops it if that queue is full.

Chunk messages (streamed text) are live only: they are neither kept in the
in-memory history nor stored. The bus knows nothing about storage: the API
registers a persister callback at startup.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentMessage:
    """A single message from an agent."""

    agent_name: str
    content: str
    timestamp: str = field(default_factory=_now)
    # agent, chunk, system, warning, error, status, decision, limit_reached
    message_type: str = "agent"
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    data: dict | None = None  # structured details, e.g. a decision's options

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "data": self.data,
        }


Persister = Callable[[str, int | None, dict], None]

# A paused run still owns the bus: no other task may start meanwhile.
BUSY = ("running", "paused")


class MessageBus:
    """Central message bus. Supports async (WebSocket) and sync (CLI) consumers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: list[AgentMessage] = []
        self._async_queues: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._sync_callbacks: list[Callable[[AgentMessage], None]] = []
        self._persister: Persister | None = None
        self._task_status: str = "idle"  # idle, running, paused, complete, stopped, error
        self._current_task: str | None = None
        self.active_project_id: str | None = None
        self.active_run_id: int | None = None

    @property
    def history(self) -> list[AgentMessage]:
        with self._lock:
            return self._history.copy()

    @property
    def task_status(self) -> str:
        return self._task_status

    @property
    def current_task(self) -> str | None:
        return self._current_task

    def set_persister(self, persister: Persister | None) -> None:
        """Register (or clear) the callback that stores non-status messages."""
        self._persister = persister

    def try_begin_task(self, task: str, project_id: str | None = None) -> bool:
        """Atomically mark a task as running in a project. False if one already is."""
        with self._lock:
            if self._task_status in BUSY:
                return False
            self._task_status = "running"
            self._current_task = task
            if project_id is not None:
                self.active_project_id = project_id
                self.active_run_id = None
        return True

    def set_task_status(self, status: str, task: str | None = None) -> None:
        """Update task status and broadcast it."""
        self._task_status = status
        if task is not None:
            self._current_task = task
        self.publish(
            AgentMessage(
                agent_name="System",
                content=f"Task status: {status}" + (f" — {task}" if task else ""),
                message_type="status",
            )
        )

    def publish(self, message: AgentMessage) -> None:
        """Publish a message to all subscribers. Safe to call from any thread."""
        live_only = message.message_type == "chunk"
        with self._lock:
            if not live_only:
                self._history.append(message)
            queues = list(self._async_queues)
            callbacks = list(self._sync_callbacks)
            project_id, run_id = self.active_project_id, self.active_run_id

        if self._persister and project_id and not live_only and message.message_type != "status":
            try:
                self._persister(project_id, run_id, message.to_dict())
            except Exception:
                log.exception("Could not save message")

        for loop, queue in queues:
            try:
                loop.call_soon_threadsafe(_put_or_drop, queue, message)
            except RuntimeError:
                self.unsubscribe_async(queue)  # its loop is closed

        for callback in callbacks:
            try:
                callback(message)
            except Exception:
                log.exception("Error in message callback")

    def subscribe_async(self) -> asyncio.Queue:
        """New async subscription. Call from inside the consuming event loop."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._async_queues.append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe_async(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._async_queues = [(lp, q) for lp, q in self._async_queues if q is not queue]

    def subscribe_sync(self, callback: Callable[[AgentMessage], None]) -> None:
        with self._lock:
            self._sync_callbacks.append(callback)

    def unsubscribe_sync(self, callback: Callable[[AgentMessage], None]) -> None:
        with self._lock:
            if callback in self._sync_callbacks:
                self._sync_callbacks.remove(callback)

    def clear_history(self) -> None:
        """Clear the in-memory view. Stored history is never touched."""
        with self._lock:
            self._history.clear()

    def set_active_project(self, project_id: str, messages: list[dict]) -> bool:
        """Switch the active project and show its stored history.

        False if a task is running in another project. While a task runs in
        this project, nothing changes (its live view stays).
        """
        loaded = []
        for msg in messages:
            try:
                loaded.append(AgentMessage(**msg))
            except TypeError:
                pass
        with self._lock:
            if self._task_status in BUSY:
                return self.active_project_id == project_id
            self.active_project_id = project_id
            self.active_run_id = None
            self._history = loaded
        return True

    def delete_project(self, project_id: str, delete: Callable[[str], bool]) -> bool | None:
        """Run `delete(project_id)` under the bus lock, so no task can start in
        the project meanwhile. None if a task is running in it; otherwise what
        `delete` returned. Deleting the active project deactivates it.

        `delete` runs while the bus lock is held. The lock isn't reentrant, so
        `delete` must not call back into the bus (publish, set_task_status,
        any property that locks): it would deadlock. Pass a store-only
        function such as `store.delete_project`.
        """
        with self._lock:
            if self._task_status in BUSY and self.active_project_id == project_id:
                return None
            deleted = delete(project_id)
            if deleted and self.active_project_id == project_id:
                self.active_project_id = None
                self.active_run_id = None
                self._history = []
            return deleted

    def start_run(self, project_id: str, run_id: int) -> None:
        """Route new messages to a run and start a fresh in-memory view."""
        with self._lock:
            self.active_project_id = project_id
            self.active_run_id = run_id
            self._history = []


def _put_or_drop(queue: asyncio.Queue, message: AgentMessage) -> None:
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        pass


# Global singleton message bus
message_bus = MessageBus()
