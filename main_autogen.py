"""
JULI — Standalone AutoGen Script.
Run this directly to execute the full 6-agent workflow.

Usage:
    python main_autogen.py "Build a secure Django + Vue web app with auth, CI/CD, tests, and monitoring"
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.agents import AGENT_ICONS
from agents.orchestrator import run_task
from agents.message_bus import message_bus, AgentMessage


def print_message(msg: AgentMessage):
    icon = AGENT_ICONS.get(msg.agent_name, "🤖")
    print(f"\n{'='*60}")
    print(f"  {icon} [{msg.agent_name}]")
    print(f"{'='*60}")
    print(msg.content)


def main():
    default_task = (
        "Build a secure Django + Vue web app with authentication, dashboard, "
        "CI/CD pipeline, automated tests, Mermaid diagrams, and real-time monitoring"
    )
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else default_task

    print("\n  🤖 J.U.L.I.")
    print("  Jolly Universe of Little Intelligences")
    print(f"  ──────────────────────────────────────")
    print(f"  📋 Task: {task[:80]}...")
    print(f"  🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    message_bus.subscribe_sync(print_message)

    try:
        messages = run_task(prompt=task, mode="full", max_round=15, work_dir="./workspace")

        os.makedirs("./workspace", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = f"./workspace/juli_output_{ts}.md"
        with open(fp, "w", encoding="utf-8") as f:
            f.write(f"# JULI Output\n**Task:** {task}\n\n---\n\n")
            for msg in messages:
                icon = AGENT_ICONS.get(msg.agent_name, "🤖")
                f.write(f"## {icon} {msg.agent_name}\n\n{msg.content}\n\n---\n\n")

        print(f"\n  💾 Output saved to: {fp}")
        print(f"  ✅ Done! ({len(messages)} messages)\n")

    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        print("  Set your API keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY")
        sys.exit(1)


if __name__ == "__main__":
    main()
