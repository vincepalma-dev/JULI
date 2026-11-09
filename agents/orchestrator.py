"""
GroupChat Orchestrator — connects 6 consolidated agents, manages conversation flow,
bridges messages to the message bus, and optionally speaks via TTS.
"""

import autogen
import threading
from typing import Dict, List, Optional
from datetime import datetime

from agents.agents import create_all_agents, create_agent_subset, AGENT_COLORS, AGENT_ICONS, AGENT_INFO
from agents.message_bus import message_bus, AgentMessage


# ─────────────────────────────────────────────────────────────
# Custom GroupChatManager with Message Bus Integration
# ─────────────────────────────────────────────────────────────

class MonitoredGroupChat(autogen.GroupChat):
    """GroupChat that emits every message to the message bus."""

    def append(self, message, speaker):
        super().append(message, speaker)
        content = message.get("content", "") if isinstance(message, dict) else str(message)
        agent_name = speaker.name if hasattr(speaker, "name") else "Unknown"

        if content and content.strip():
            message_bus.publish(AgentMessage(
                agent_name=agent_name,
                content=content,
                timestamp=datetime.now().isoformat(),
                message_type="agent",
            ))


# ─────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────

def create_group_chat(agents: Dict[str, autogen.Agent], max_round: int = 15) -> tuple:
    """Create GroupChat + GroupChatManager."""
    agent_list = list(agents.values())
    first_agent_key = [k for k in agents if k != "UserProxy"][0]

    group_chat = MonitoredGroupChat(
        agents=agent_list,
        messages=[],
        max_round=max_round,
        speaker_selection_method="auto",
        allow_repeat_speaker=False,
    )

    manager = autogen.GroupChatManager(
        groupchat=group_chat,
        llm_config={
            "config_list": agents[first_agent_key].llm_config["config_list"],
            "temperature": 0.2,
            "timeout": 120,
            "cache_seed": None,
        },
    )
    return group_chat, manager


def run_task(
    prompt: str,
    mode: str = "full",
    max_round: int = 15,
    work_dir: str = "./workspace",
    no_devops: bool = False,
    voice: bool = False,
) -> List[AgentMessage]:
    """
    Run a task through the multi-agent system.

    Args:
        prompt: Task description
        mode: 'full', 'plan', 'code', or 'review'
        max_round: Max conversation rounds
        work_dir: Code execution directory
        no_devops: Skip DevOps agent
        voice: Enable TTS voice output
    """
    message_bus.set_task_status("running", prompt)

    # Register voice callback if enabled
    voice_callback = None
    if voice:
        try:
            from agents.utils import speak
            def voice_callback(msg):
                if msg.message_type == "agent" and msg.agent_name not in ("UserProxy", "System"):
                    speak(msg.content, msg.agent_name)
            message_bus.subscribe_sync(voice_callback)
        except ImportError:
            pass

    try:
        # Select agents by mode
        if mode == "plan":
            agent_names = ["PlannerResearcher", "DocsDiagram"]
        elif mode == "code":
            agent_names = ["PlannerResearcher", "Coder", "ReviewerSecurity"]
        elif mode == "review":
            agent_names = ["ReviewerSecurity"]
        else:
            agent_names = [
                "PlannerResearcher", "Coder", "ReviewerSecurity",
                "DevOps", "TestMonitor", "DocsDiagram",
            ]

        if no_devops and "DevOps" in agent_names:
            agent_names.remove("DevOps")

        agents = create_agent_subset(agent_names, work_dir)

        message_bus.publish(AgentMessage(
            agent_name="System",
            content=f"Activating agents: {', '.join(agent_names)}",
            message_type="system",
        ))

        group_chat, manager = create_group_chat(agents, max_round)
        agents["UserProxy"].initiate_chat(manager, message=prompt)

        message_bus.set_task_status("complete")

    except Exception as e:
        message_bus.publish(AgentMessage(
            agent_name="System",
            content=f"Error: {str(e)}",
            message_type="error",
        ))
        message_bus.set_task_status("error")
    finally:
        if voice_callback:
            message_bus.unsubscribe_sync(voice_callback)

    return message_bus.history


def run_task_async(prompt: str, **kwargs) -> threading.Thread:
    """Run task in background thread (for dashboard)."""
    thread = threading.Thread(target=run_task, args=(prompt,), kwargs=kwargs, daemon=True)
    thread.start()
    return thread


def get_agent_info() -> List[dict]:
    """Get metadata about all available agents."""
    return AGENT_INFO
