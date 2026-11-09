"""
JULI command line. Run it with `python -m juli` (entry point: main).

It drives the same engine as the dashboard: the crew and limits come from
settings, runs are stored in the same database (project "CLI" by default),
and each agent's reply streams as it arrives.
"""

import os
import queue
import threading
from datetime import datetime

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from juli import config, engine, store
from juli.bus import AgentMessage, message_bus

app = typer.Typer(name="juli", help="JULI: a local-first crew of AI agents.", add_completion=False)
console = Console()

STYLES = {"system": "dim", "warning": "yellow", "error": "bold red", "limit_reached": "bold yellow", "decision": "bold cyan"}


class Printer:
    """Prints bus messages: streamed chunks inline, a usage line after each turn."""

    def __init__(self, colors: dict[str, str]) -> None:
        self.colors = colors
        self.streaming: str | None = None

    def __call__(self, msg: AgentMessage) -> None:
        kind = msg.message_type
        if kind == "status":
            return
        if kind == "turn_start":
            self._end_line()
            color = self.colors.get(msg.agent_name, "white")
            activity = (msg.data or {}).get("activity", "working")
            console.print(f"\n[bold {color}]{escape(msg.agent_name)}[/]  [dim]{escape(msg.model or '')} · {activity}…[/]")
            self.streaming = msg.agent_name
            return
        if kind == "chunk":
            if self.streaming != msg.agent_name:
                self._end_line()
                color = self.colors.get(msg.agent_name, "white")
                console.print(f"\n[bold {color}]{msg.agent_name}[/]  [dim]{msg.model or ''}[/]")
                self.streaming = msg.agent_name
            console.out(msg.content, end="", highlight=False)
            return
        self._end_line()
        if kind == "agent":
            cost = "" if msg.cost_usd is None else f" · ${msg.cost_usd:.4f}"
            console.print(f"[dim]{msg.tokens_in or 0} tokens in · {msg.tokens_out or 0} out{cost}[/]")
        else:
            console.print(msg.content, style=STYLES.get(kind, ""), markup=False)

    def _end_line(self) -> None:
        if self.streaming:
            console.out("")
            self.streaming = None


def _answer(msg: AgentMessage) -> None:
    """Prompt for a paused run's decision until the engine accepts an answer."""
    data = msg.data or {}
    while True:
        if data.get("kind") == "plan_approval":
            answer = typer.prompt("Approve the plan? [y]es / [n]o, stop / or type changes", default="y").strip()
            if answer.lower() in ("y", "yes"):
                error = engine.decide("approve")
            elif answer.lower() in ("n", "no", "stop"):
                error = engine.decide("stop")
            else:
                error = engine.decide("revise", message=answer)
        else:
            model = typer.prompt("Switch to which model (provider:model)? Leave empty to stop", default="", show_default=False)
            error = engine.decide("switch", model.strip()) if model.strip() else engine.decide("stop")
        if error is None or error in ("No decision is pending", "No task is running"):
            return
        console.print(error, style="red", markup=False)


def save_output(messages: list[AgentMessage], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"juli_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# JULI output, {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        for msg in messages:
            if msg.message_type == "agent":
                f.write(f"## {msg.agent_name}\n\n{msg.content}\n\n---\n\n")
    return path


def run_task(
    prompt: str,
    mode: str,
    *,
    project: str,
    max_cycles: int,
    approve_plan: bool,
    discussion_rounds: int | None,
    no_devops: bool,
    ignore_allowance: bool,
    voice: bool,
    output_dir: str,
) -> None:
    store.init_db()
    config.migrate_legacy_settings()
    settings = config.load_settings()
    project_id = store.find_or_create_project(project)
    run = engine.Run(
        prompt,
        mode,
        engine.build_crew(settings),
        settings=settings,
        max_cycles=max_cycles,
        approve_plan=approve_plan,
        discussion_rounds=discussion_rounds,
        no_devops=no_devops,
        review_source=engine.review_source(project_id) if mode == "review" else "",
    )
    warnings, blocked = engine.allowance_report(run.agents, settings)
    if blocked and not ignore_allowance:
        for line in blocked:
            console.print(f"Monthly allowance reached: {line}.", style="red", markup=False)
        console.print("Run again with --ignore-allowance to continue.")
        raise typer.Exit(1)
    run.notices = warnings + blocked

    colors = {name: cfg.get("color", "white") for name, cfg in settings["agents"].items()}
    console.print(f"[bold]Mode:[/] {mode}   [bold]Project:[/] {escape(project)}")
    console.print(f"[bold]Task:[/] {escape(prompt)}", highlight=False)

    message_bus.set_persister(store.save_message)
    decisions: queue.Queue = queue.Queue()
    printer = Printer(colors)

    def on_message(msg: AgentMessage) -> None:
        if msg.message_type == "decision":
            decisions.put(msg)
        if voice and msg.message_type == "agent":
            from juli.voice import speak

            speak(msg.content, msg.agent_name)

    run_id = engine.begin(project_id, run)
    if run_id is None:
        message_bus.set_persister(None)
        console.print("A task is already running.", style="red")
        raise typer.Exit(1)
    message_bus.subscribe_sync(printer)
    message_bus.subscribe_sync(on_message)

    results: list[engine.RunResult] = []
    worker = threading.Thread(target=lambda: results.append(engine.execute(run)), daemon=True)
    worker.start()
    stopped = False
    try:
        while worker.is_alive():
            try:
                _answer(decisions.get(timeout=0.2))
            except queue.Empty:
                pass
    except (KeyboardInterrupt, typer.Abort):  # Ctrl+C, also inside a prompt
        stopped = True
        console.print("\nStopping...", style="yellow")
        engine.stop()
        try:
            worker.join()
        except KeyboardInterrupt:
            pass  # a second Ctrl+C: finish up without waiting
    finally:
        message_bus.unsubscribe_sync(printer)
        message_bus.unsubscribe_sync(on_message)
        message_bus.set_persister(None)

    result = results[0] if results else engine.RunResult("stopped" if stopped else "error")
    store.finish_run(run_id, result.status, result.tokens_in, result.tokens_out, result.cost_usd)
    console.print(
        f"\n[bold]Run {result.status}[/]  {result.tokens_in} tokens in · {result.tokens_out} out · ${result.cost_usd:.4f}"
    )
    console.print(f"Saved to {save_output(message_bus.history, output_dir)}", highlight=False)
    if result.status == "error":
        raise typer.Exit(1)


@app.command()
def run(
    prompt: str = typer.Argument(..., help="What the crew should build"),
    plan: bool = typer.Option(False, "--plan", "-p", help="Plan only (planner, then docs)"),
    code: bool = typer.Option(False, "--code", "-c", help="Plan, then code and review"),
    review: bool = typer.Option(False, "--review", "-r", help="Review the project's latest run; the prompt says what to focus on"),
    project: str = typer.Option("CLI", "--project", help="Project to store the run in"),
    max_cycles: int = typer.Option(3, "--max-cycles", min=1, max=10, help="Code-review cycles at most"),
    approve_plan: bool = typer.Option(False, "--approve-plan", help="Pause after the plan to approve or change it"),
    discuss: int | None = typer.Option(None, "--discuss", min=0, max=4, help="Crew discussion rounds on the plan (0 is off; default from settings)"),
    no_devops: bool = typer.Option(False, "--no-devops", help="Skip the DevOps agent"),
    ignore_allowance: bool = typer.Option(False, "--ignore-allowance", help="Run even if a monthly allowance is used up"),
    voice: bool = typer.Option(False, "--voice", "-v", help="Speak each agent's reply"),
    output_dir: str = typer.Option("./workspace", "--output", "-o", help="Where to save the transcript"),
) -> None:
    """Run the crew on a task."""
    mode = "plan" if plan else "code" if code else "review" if review else "full"
    run_task(
        prompt,
        mode,
        project=project,
        max_cycles=max_cycles,
        approve_plan=approve_plan,
        discussion_rounds=discuss,
        no_devops=no_devops,
        ignore_allowance=ignore_allowance,
        voice=voice,
        output_dir=output_dir,
    )


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Your question about the run"),
    agent: str = typer.Option("PlannerResearcher", "--agent", "-a", help="Which agent answers"),
    project: str = typer.Option("CLI", "--project", help="Project whose latest run to ask about"),
    run_id: int | None = typer.Option(None, "--run", help="A specific run id instead of the latest"),
) -> None:
    """Ask an agent a follow-up question about a finished run."""
    from juli import providers

    store.init_db()
    settings = config.load_settings()
    if agent not in settings["agents"]:
        console.print(f"No agent named {agent}.", style="red", markup=False)
        raise typer.Exit(1)
    if run_id is None:
        runs = [r for r in store.get_runs(store.find_or_create_project(project)) if r["ended_at"]]
        run_id = runs[-1]["id"] if runs else None
    run_row = store.get_run(run_id) if run_id is not None else None
    if not run_row or not run_row["ended_at"]:
        console.print("No finished run to ask about.", style="red")
        raise typer.Exit(1)
    try:
        answer = engine.follow_up(run_row, agent, question, settings)
    except (providers.ProviderError, providers.PrivacyViolation) as e:
        console.print(providers.redact(str(e)), style="red", markup=False)
        raise typer.Exit(1) from None
    console.print(answer["reply"], markup=False, highlight=False)
    cost = "" if answer["cost_usd"] is None else f" · ${answer['cost_usd']:.4f}"
    console.print(f"[dim]{answer['model']} · {answer['tokens_in']} tokens in · {answer['tokens_out']} out{cost}[/]")


@app.command("agents")
def list_agents() -> None:
    """List the crew from settings."""
    table = Table(title="JULI crew")
    for column in ("Agent", "Role", "Model", "Max output"):
        table.add_column(column)
    for agent in engine.build_crew(config.load_settings()):
        table.add_row(agent.name, agent.role, agent.model, str(agent.max_tokens or ""))
    console.print(table)


@app.command("voice")
def voice_task(prompt: str = typer.Argument(..., help='Task prompt, or "listen" to speak it')) -> None:
    """Run the full crew and speak each reply. "listen" takes the prompt by voice."""
    if prompt == "listen":
        from juli.voice import listen

        heard = listen()
        if not heard:
            console.print("Couldn't capture a voice prompt. Type it instead.", style="red")
            raise typer.Exit(1)
        prompt = heard
    run_task(
        prompt,
        "full",
        project="CLI",
        max_cycles=3,
        approve_plan=False,
        discussion_rounds=None,
        no_devops=False,
        ignore_allowance=False,
        voice=True,
        output_dir="./workspace",
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
