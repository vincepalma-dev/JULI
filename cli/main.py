"""
JULI — CLI Tool.
Color-coded terminal interface for the 6-agent AI development team.
"""

import os
import sys
import typer
from pathlib import Path
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.rule import Rule

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from juli.bus import message_bus, AgentMessage
from agents.orchestrator import run_task, get_agent_info
from agents.agents import AGENT_ICONS

app = typer.Typer(
    name="ai-dev",
    help="🤖 JULI — Elite AI Development Team CLI",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

RICH_COLORS = {
    "PlannerResearcher": "bright_blue",
    "Coder": "bright_cyan",
    "ReviewerSecurity": "bright_red",
    "DevOps": "bright_green",
    "TestMonitor": "yellow",
    "DocsDiagram": "bright_magenta",
    "UserProxy": "grey62",
    "System": "dim",
}


def print_header():
    console.print()
    console.print(Panel.fit(
        "[bold bright_cyan]🤖 J.U.L.I.[/bold bright_cyan]\n"
        "[dim]Jolly Universe of Little Intelligences[/dim]\n"
        "[bright_blue]Elite AI Development Team[/bright_blue]",
        border_style="bright_cyan",
        padding=(1, 4),
    ))
    console.print()


def print_agent_message(msg: AgentMessage):
    color = RICH_COLORS.get(msg.agent_name, "white")
    icon = AGENT_ICONS.get(msg.agent_name, "🤖")
    ts = msg.timestamp.split("T")[-1][:8] if "T" in msg.timestamp else ""

    console.print(f"  {icon} [{color} bold][{msg.agent_name}][/{color} bold]  [dim]{ts}[/dim]")
    content = msg.content.strip()[:2000]
    if "```" in content:
        console.print(Markdown(content))
    else:
        for line in content.split("\n"):
            console.print(f"    {line}")
    console.print()


def save_output(messages, output_dir="./workspace"):
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = os.path.join(output_dir, f"juli_output_{ts}.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(f"# JULI Output — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        for msg in messages:
            if isinstance(msg, AgentMessage):
                icon = AGENT_ICONS.get(msg.agent_name, "🤖")
                f.write(f"## {icon} {msg.agent_name}\n\n{msg.content}\n\n---\n\n")
    console.print(f"  💾 Saved to [bright_cyan]{fp}[/bright_cyan]")
    return fp


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Task prompt for the AI team"),
    plan: bool = typer.Option(False, "--plan", "-p", help="Planner only"),
    code: bool = typer.Option(False, "--code", "-c", help="Coding pipeline only"),
    review: bool = typer.Option(False, "--review", "-r", help="Review last output"),
    no_devops: bool = typer.Option(False, "--no-devops", help="Skip DevOps agent"),
    voice: bool = typer.Option(False, "--voice", "-v", help="Enable voice (TTS) output"),
    max_rounds: int = typer.Option(15, "--max-rounds", "-m", help="Max rounds"),
    output_dir: str = typer.Option("./workspace", "--output", "-o", help="Output dir"),
    push: bool = typer.Option(False, "--push", help="Auto-push to GitHub"),
):
    """🤖 Run the JULI elite development team on a task."""
    print_header()

    mode = "plan" if plan else "code" if code else "review" if review else "full"
    mode_labels = {"full": "🚀 Full Team", "plan": "🏗️ Plan", "code": "💻 Code", "review": "🛡️ Review"}

    console.print(f"  [bold]Mode:[/bold] {mode_labels.get(mode)}")
    console.print(f"  [bold]Task:[/bold] {prompt}")
    if voice:
        console.print("  [bold]Voice:[/bold] [bright_green]Enabled[/bright_green]")
    console.print()

    # Show agents table
    table = Table(show_header=True, header_style="bold bright_cyan", box=None)
    table.add_column("", width=3)
    table.add_column("Agent", style="bold")
    table.add_column("Model", style="dim")
    for a in get_agent_info():
        table.add_row(a["icon"], a["name"], a["model"])
    console.print(Panel(table, title="[bold]Agents[/bold]", border_style="bright_blue"))
    console.print()

    message_bus.subscribe_sync(print_agent_message)
    console.print(Rule("[bold bright_cyan]Agent Conversation[/bold bright_cyan]"))
    console.print()

    try:
        messages = run_task(prompt=prompt, mode=mode, max_round=max_rounds,
                           work_dir=output_dir, no_devops=no_devops, voice=voice)
    except Exception as e:
        console.print(f"  ❌ [bright_red]Error: {e}[/bright_red]")
        raise typer.Exit(1)

    console.print()
    console.print(Rule("[bold bright_green]Task Complete[/bold bright_green]"))
    save_output(messages, output_dir)

    if push:
        from agents.utils import git_add_commit, git_push
        try:
            git_add_commit(f"JULI: {prompt[:50]}")
            git_push()
            console.print("  ✅ [bright_green]Pushed to GitHub[/bright_green]")
        except Exception as e:
            console.print(f"  ❌ [bright_red]Git push failed: {e}[/bright_red]")
    console.print()


@app.command("agents")
def list_agents():
    """📋 List all agents."""
    print_header()
    table = Table(title="[bold bright_cyan]JULI Agents[/bold bright_cyan]", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("", width=3)
    table.add_column("Agent", style="bold")
    table.add_column("Model")
    for i, a in enumerate(get_agent_info(), 1):
        c = RICH_COLORS.get(a["name"], "white")
        table.add_row(str(i), a["icon"], f"[{c}]{a['name']}[/{c}]", a["model"])
    console.print(table)


@app.command("voice")
def voice_task(prompt: str = typer.Argument(..., help="Task prompt")):
    """🎙️ Run task with voice interface (TTS + optional STT)."""
    print_header()
    console.print("  🎤 [bold]Voice Mode Active[/bold]")

    # Try STT if no prompt given
    if prompt == "listen":
        from agents.utils import listen
        heard = listen()
        if heard:
            prompt = heard
        else:
            console.print("  ❌ Could not capture voice. Use text input instead.")
            raise typer.Exit(1)

    console.print(f"  📋 Task: {prompt}\n")
    message_bus.subscribe_sync(print_agent_message)
    run_task(prompt=prompt, mode="full", voice=True)
    console.print("\n  ✅ [bold bright_green]Voice task complete![/bold bright_green]\n")


def main():
    app()

if __name__ == "__main__":
    main()
