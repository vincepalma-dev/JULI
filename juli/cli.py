"""
JULI command line. Run it with `python -m juli` (entry point: main).

It drives the same engine as the dashboard: the crew and limits come from
settings, runs are stored in the same database (project "CLI" by default),
and each agent's reply streams as it arrives.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from juli import config, engine, keystore, providers, store, terminal, workspace
from juli.bus import AgentMessage, message_bus
from juli.local import catalogue, crew, hardware, ollama

app = typer.Typer(name="juli", help="JULI: a local-first crew of AI agents.", add_completion=False)
models_app = typer.Typer(help="On-device models: installed, catalogue, downloads, benchmarks.", no_args_is_help=True)
endpoint_app = typer.Typer(help="Custom OpenAI-compatible endpoints (LM Studio, llama.cpp, vLLM...).", no_args_is_help=True)
workspace_app = typer.Typer(help="A project's files: tree, diff, zip, commit to a run branch, push.", no_args_is_help=True)
app.add_typer(models_app, name="models")
app.add_typer(endpoint_app, name="endpoint")
app.add_typer(workspace_app, name="workspace")
console = Console()

STYLES = {
    "system": "dim",
    "warning": "yellow",
    "error": "bold red",
    "limit_reached": "bold yellow",
    "decision": "bold cyan",
    "files": "green",
    "command": "cyan",
}


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
        if kind == "command_output":
            console.out(msg.content, end="", highlight=False, style="dim")
            return
        self._end_line()
        if kind == "agent":
            cost = "" if msg.cost_usd is None else f" · ${msg.cost_usd:.4f}"
            console.print(f"[dim]{msg.tokens_in or 0} tokens in · {msg.tokens_out or 0} out{cost}[/]")
        elif kind == "command_start":
            where = "sandbox" if (msg.data or {}).get("sandbox") else "this machine"
            console.print(f"\n[bold]$ {escape(msg.content)}[/]  [dim]{where}[/]")
        elif kind == "command":
            # The output already streamed; show the command and its status.
            console.print(msg.content.split("\n\n")[0], style=STYLES["command"], markup=False)
        elif kind == "tool_start":
            console.print(f"[dim]→ {escape(msg.content)}[/]")
        elif kind == "tool":
            status = (msg.data or {}).get("status", "ok")
            if status != "ok":
                console.print(f"[dim]  {escape(msg.content)}: {escape(status)}[/]")
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
        elif data.get("kind") == "command_approval":
            error = engine.decide("approve" if typer.confirm("Run this command?", default=False) else "deny")
        elif data.get("kind") == "tool_approval":
            error = engine.decide("approve" if typer.confirm("Allow this tool call?", default=False) else "deny")
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
    _check_allowance(run, settings, ignore_allowance)
    console.print(f"[bold]Mode:[/] {mode}   [bold]Project:[/] {escape(project)}")
    console.print(f"[bold]Task:[/] {escape(prompt)}", highlight=False)
    _drive(run, project_id, settings, voice=voice, output_dir=output_dir)


def _check_allowance(run: engine.Run, settings: dict, ignore_allowance: bool) -> None:
    warnings, blocked = engine.allowance_report(run.agents, settings)
    if blocked and not ignore_allowance:
        for line in blocked:
            console.print(f"Monthly allowance reached: {line}.", style="red", markup=False)
        console.print("Run again with --ignore-allowance to continue.")
        raise typer.Exit(1)
    run.notices = warnings + blocked


def _drive(run: engine.Run, project_id: str, settings: dict, *, voice: bool, output_dir: str, run_id: int | None = None) -> None:
    """Run to the end, printing it and answering its pauses; `run_id` resumes that run."""
    colors = {name: cfg.get("color", "white") for name, cfg in settings["agents"].items()}
    message_bus.set_persister(store.save_message)
    decisions: queue.Queue = queue.Queue()
    printer = Printer(colors)

    def on_message(msg: AgentMessage) -> None:
        if msg.message_type == "decision":
            decisions.put(msg)
        if voice and msg.message_type == "agent":
            from juli.voice import speak

            speak(msg.content, msg.agent_name)

    run_id = engine.begin(project_id, run, run_id)
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
    console.print(f"\n[bold]Run {result.status}[/]  {result.tokens_in} tokens in · {result.tokens_out} out · ${result.cost_usd:.4f}")
    console.print(f"Saved to {save_output(message_bus.history, output_dir)}", highlight=False)
    if result.status == "error":
        console.print(f"Fix the cause, then `juli resume {run_id}` continues from the last finished step.")
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
    discuss: int | None = typer.Option(
        None, "--discuss", min=0, max=4, help="Crew discussion rounds on the plan (0 is off; default from settings)"
    ),
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


@app.command("resume")
def resume(
    run_id: int | None = typer.Argument(None, help="The run to resume; default is the project's latest resumable run"),
    project: str = typer.Option("CLI", "--project", help="Project to look in when no run is given"),
    list_only: bool = typer.Option(False, "--list", help="Only list the runs that can resume"),
    ignore_allowance: bool = typer.Option(False, "--ignore-allowance", help="Run even if a monthly allowance is used up"),
    voice: bool = typer.Option(False, "--voice", "-v", help="Speak each agent's reply"),
    output_dir: str = typer.Option("./workspace", "--output", "-o", help="Where to save the transcript"),
) -> None:
    """Resume a run that a restart, crash or error cut short, from its last finished step."""
    store.init_db()
    config.migrate_legacy_settings()
    if list_only or run_id is None:
        runs = store.resumable_runs(store.find_or_create_project(project))
        if list_only:
            table = Table(title="Runs that can resume")
            for column in ("Run", "Status", "Mode", "Started", "Task"):
                table.add_column(column)
            for r in runs:
                table.add_row(str(r["id"]), r["status"], r["mode"], r["started_at"][:16], r["prompt"][:60])
            console.print(table if runs else "No run in this project can resume.")
            return
        if not runs:
            console.print("No run in this project can resume.", style="red")
            raise typer.Exit(1)
        run_id = runs[0]["id"]
    row, checkpoint = store.get_run(run_id), store.get_checkpoint(run_id)
    if not row or not checkpoint or row["status"] not in store.RESUMABLE:
        console.print(f"Run {run_id} has no checkpoint to resume from.", style="red")
        raise typer.Exit(1)
    settings = config.load_settings()
    try:
        run = engine.Run.from_checkpoint(json.loads(checkpoint), settings=settings)
    except (ValueError, KeyError, TypeError) as e:
        console.print(f"The checkpoint can't be used: {e}", style="red", markup=False)
        raise typer.Exit(1) from None
    _check_allowance(run, settings, ignore_allowance)
    console.print(f"[bold]Resuming run {run_id}:[/] {escape(row['prompt'])}", highlight=False)
    _drive(run, row["project_id"], settings, voice=voice, output_dir=output_dir, run_id=run_id)


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


FRONTEND_DIR = config.ROOT_DIR / "frontend"


def build_dashboard() -> None:
    """npm run build in frontend/ (npm install first if needed)."""
    if not FRONTEND_DIR.is_dir():
        # Only a clone of the repository has the dashboard's sources (an editable install).
        console.print(
            "The dashboard's sources aren't here. JULI runs from a clone of its repository: "
            "git clone https://github.com/vincepalma-dev/JULI.git, then pip install -e . in that folder.",
            style="red",
        )
        raise typer.Exit(1)
    npm = shutil.which("npm")
    if not npm:
        console.print("Node.js is needed to build the dashboard. Install it from https://nodejs.org", style="red")
        raise typer.Exit(1)
    try:
        if not (FRONTEND_DIR / "node_modules").is_dir():
            console.print("Installing the dashboard's packages...")
            subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)
        console.print("Building the dashboard...")
        subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)
    except subprocess.CalledProcessError:
        console.print("The dashboard build failed; see the output above.", style="red")
        raise typer.Exit(1) from None


@app.command("serve")
def serve(
    port: int = typer.Option(8000, "--port", min=1, max=65535, help="Port on 127.0.0.1"),
    build: bool = typer.Option(False, "--build", help="Rebuild the dashboard first"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the dashboard"),
    show_link: bool = typer.Option(False, "--show-link", help="Print the dashboard link, which holds the session token"),
) -> None:
    """Serve the dashboard and the API on one origin, http://127.0.0.1:<port>, and open it."""
    import secrets
    import webbrowser

    import uvicorn

    from juli.api.app import create_app

    dist = FRONTEND_DIR / "dist"
    if build or not (dist / "index.html").is_file():
        build_dashboard()
    origin = f"http://127.0.0.1:{port}"
    # The dashboard's own origins must pass the WebSocket Origin check. The default
    # allowlist covers ports 3000 and 8000; a list the user set is kept and extended.
    existing = [o.strip() for o in os.environ.get("JULI_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if existing or port != 8000:
        served = [origin, f"http://localhost:{port}"]
        os.environ["JULI_ALLOWED_ORIGINS"] = ",".join(dict.fromkeys(existing + served))
    token = secrets.token_urlsafe(32)
    link = f"{origin}/#token={token}"
    server = uvicorn.Server(uvicorn.Config(create_app(token, static_dir=dist, port=port), host="127.0.0.1", port=port))

    def open_when_up() -> None:
        while not server.started and not server.should_exit:
            time.sleep(0.1)
        if not server.started:
            return
        # The link holds the session token, so it's only printed on request.
        if show_link:
            console.print("Dashboard link (keep it private, it holds your session token):")
            console.print(link, markup=False, highlight=False, soft_wrap=True)
        if not no_browser:
            webbrowser.open(link)
        elif not show_link:
            console.print("JULI is running. Restart with --show-link to print the dashboard link.")

    threading.Thread(target=open_when_up, daemon=True).start()
    console.print(f"JULI on {origin} (Ctrl+C stops it)")
    server.run()


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


# ─── On-device models ────────────────────────────────────────


def _endpoints() -> dict | None:
    return config.load_settings().get("endpoints")


@contextmanager
def _upstream() -> Iterator[None]:
    """Ollama, Hugging Face and settings failures as a short message and exit 1."""
    try:
        yield
    except httpx.HTTPError:
        console.print(f"Ollama isn't running at {ollama.base_url(_endpoints())}. Start it with `ollama serve`.", style="red", markup=False)
        raise typer.Exit(1) from None
    except (providers.ProviderError, ValueError, keystore.KeystoreUnavailable) as e:
        console.print(str(e), style="red", markup=False)
        raise typer.Exit(1) from None


def _gb(value: float | None) -> str:
    return "" if value is None else f"{value:.1f} GB"


def _fit_text(fit: dict) -> str:
    if fit["tier"] == "cannot":
        return f"[red]cannot[/] [dim]{escape(fit['reason'])}[/]"
    color = "green" if fit["tier"] == "great" else "yellow"
    return f"[{color}]{fit['tier']}[/] [dim]ctx {fit['num_ctx'] // 1024}K[/]"


@app.command("hardware")
def show_hardware() -> None:
    """What this machine has for running models."""
    hw = hardware.current()
    gpu_gb, total_gb = hardware.budgets(hw)
    gpu = hw["gpu"]
    gpu_text = f"{gpu['name']}, {_gb(gpu['vram_gb'])}" + (" unified" if gpu["unified"] else "") if gpu else "none (models run on the CPU)"
    table = Table(title="This machine", show_header=False)
    table.add_row("CPU", f"{hw['cpu']} ({hw['cores']} cores)")
    table.add_row("RAM", _gb(hw["ram_gb"]))
    table.add_row("GPU", gpu_text)
    table.add_row("Disk free", f"{_gb(hw['disk_free_gb'])} in {hw['models_dir']}")
    table.add_row("Model budget", f"GPU {_gb(gpu_gb)} · total {_gb(total_gb)}")
    table.add_row("Fingerprint", hw["fingerprint"])
    console.print(table)


@models_app.command("list")
def list_models() -> None:
    """Installed models, which are loaded, and their measured speed."""
    endpoints = _endpoints()
    with _upstream():
        tags, loaded = ollama.tags(endpoints), {m.get("name") for m in ollama.ps(endpoints)}
    if not tags:
        console.print("No models installed yet. Try `juli models catalogue`.")
        return
    store.init_db()
    speeds = store.get_benchmarks(hardware.current()["fingerprint"])
    table = Table(title="Installed models")
    for column in ("Model", "Size", "Quant", "Loaded", "Speed"):
        table.add_column(column)
    for model in tags:
        bench = speeds.get(f"ollama:{model['name']}")
        table.add_row(
            model["name"],
            _gb(model.get("size", 0) / 1e9),
            (model.get("details") or {}).get("quantization_level", ""),
            "yes" if model["name"] in loaded else "",
            f"{bench['tok_per_sec']:.1f} tok/s" if bench else "",
        )
    console.print(table)


@models_app.command("catalogue")
def show_catalogue() -> None:
    """The model catalogue, with how well each model fits this machine."""
    settings = config.load_settings()
    hw = hardware.current()
    table = Table(title="Catalogue")
    for column in ("Model", "Size", "Context", "License", "Roles", "Fit", ""):
        table.add_column(column)
    for m in catalogue.listing(hw, ollama.installed(settings.get("endpoints")), settings):
        lic = m["license"]
        license_text = escape(lic["name"]) + (" [dim](accept)[/]" if lic["accept"] and not lic["accepted"] else "")
        table.add_row(
            m["tag"],
            _gb(m["size_gb"]),
            f"{m['context_max'] // 1024}K",
            license_text,
            ", ".join(m["roles"]),
            _fit_text(m["fit"]),
            "installed" if m["installed"] else "",
        )
    console.print(table)


def _ensure_license(model: str, accept: bool) -> None:
    with _upstream():
        lic = catalogue.license_needed(model, config.load_settings())
    if not lic:
        return
    console.print(f"{model} is under {lic['name']}: {lic['url']}", markup=False)
    if not accept and not typer.confirm("Do you accept these terms?", default=False):
        console.print("Not downloaded.")
        raise typer.Exit(1)
    with _upstream():
        catalogue.accept_license(lic["id"])


@models_app.command("pull")
def pull_model(
    model: str = typer.Argument(..., help="e.g. qwen3:8b or hf.co/owner/repo:Q4_K_M"),
    accept_license: bool = typer.Option(False, "--accept-license", help="Accept the model's license without asking"),
) -> None:
    """Download a model. Ctrl+C stops; running it again resumes."""
    _ensure_license(model, accept_license)
    columns = (TextColumn("{task.description}"), BarColumn(), DownloadColumn(), TransferSpeedColumn())
    with Progress(*columns, console=console) as progress:
        task = progress.add_task(escape(model), total=None)

        def show(p: dict) -> None:
            description = f"{escape(model)} [dim]{escape(p['status'][:40])}[/]"
            progress.update(task, description=description, completed=p["completed"], total=p["total"] or None)

        try:
            with _upstream():
                ollama.pull(model, show, endpoints=_endpoints())
        except KeyboardInterrupt:
            progress.stop()
            console.print("Stopped. Run the same command again to resume.", style="yellow")
            raise typer.Exit(1) from None
    console.print(f"{model} is installed.", markup=False)


@models_app.command("rm")
def remove_model(
    model: str = typer.Argument(..., help="The installed model to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask first"),
) -> None:
    """Delete an installed model from disk."""
    if not yes and not typer.confirm(f"Delete {model} from disk? Downloading it again takes a while.", default=False):
        raise typer.Exit(1)
    with _upstream():
        ollama.delete(model, _endpoints())
    console.print(f"Deleted {model}.", markup=False)


@models_app.command("bench")
def bench_model(model: str = typer.Argument(..., help="An installed model")) -> None:
    """Measure a model's speed on this machine."""
    store.init_db()
    with console.status(f"Benchmarking {escape(model)}…"), _upstream():
        result = ollama.benchmark(model, _endpoints())
    prefill = result["prefill_tok_per_sec"]
    line = f"{model}: {result['tok_per_sec']:.1f} tok/s" + (f" · prefill {prefill:.0f} tok/s" if prefill else "")
    console.print(line, markup=False)


@models_app.command("hf")
def hugging_face(repo: str = typer.Argument(..., help="A Hugging Face repo, e.g. bartowski/Llama-3.2-1B-Instruct-GGUF")) -> None:
    """List a Hugging Face repo's GGUF files with how well each fits."""
    settings = config.load_settings()
    with _upstream():
        found = catalogue.hf_models(repo, hardware.current(), ollama.installed(settings.get("endpoints")), settings)
    lic = found["license"]
    needs = " (needs acceptance)" if lic["accept"] and not lic["accepted"] else ""
    console.print(f"License: {lic['name']}{needs}", markup=False)
    if not found["models"]:
        console.print("No GGUF files in this repo.")
        return
    table = Table(title=escape(repo))
    for column in ("Pull as", "Size", "Fit"):
        table.add_column(column)
    for m in found["models"]:
        table.add_row(m["tag"], _gb(m["size_gb"]), _fit_text(m["fit"]))
    console.print(table)


@app.command("auto-crew")
def auto_crew(
    agent: list[str] | None = typer.Option(None, "--agent", "-a", help="Only this agent (repeatable); default is every agent"),
    apply: bool = typer.Option(False, "--apply", help="Save the picks to settings"),
    set_fallback: bool = typer.Option(False, "--set-fallback", help="Also make the best general model the local fallback"),
) -> None:
    """Pick a local model per agent that fits this machine."""
    with _upstream():
        result = crew.run_auto_crew(agent or None, apply=apply, set_fallback=set_fallback)
    table = Table(title="Auto-Crew")
    for column in ("Agent", "Model", "Fit", "Context", ""):
        table.add_column(column)
    for name, pick in result["agents"].items():
        if pick:
            size = "installed" if pick["installed"] else _gb(pick["size_gb"])
            table.add_row(name, pick["model"], pick["tier"], f"{pick['num_ctx'] // 1024}K", size)
        else:
            table.add_row(name, "[red]nothing fits[/]", "", "", "")
    console.print(table)
    for warning in result["warnings"]:
        console.print(warning, style="yellow", markup=False)
    if result["shared"]:
        console.print("The downloads don't all fit on disk, so every agent shares one model.", style="yellow")
    if result["downloads"]:
        console.print(
            f"To download: {', '.join(result['downloads'])} ({_gb(result['download_gb'])}). Use `juli models pull`.", markup=False
        )
    for lic in result["licenses"]:
        console.print(f"Needs acceptance before download: {lic['name']} ({lic['url']})", markup=False)
    console.print("Saved." if apply else "Run with --apply to save these picks.")


@app.command("mode")
def mode(
    name: str | None = typer.Argument(None, help="privacy, hybrid or cloud; leave out to show the current mode"),
    cloud_model: str | None = typer.Option(None, "--cloud-model", help="The cloud model for agents that move to the cloud"),
) -> None:
    """Show or switch Privacy (all local), Hybrid (Plan and Review in the cloud) or Cloud mode."""
    if name is None:
        console.print(f"Mode: {crew.current_mode(config.load_settings())}")
        return
    with _upstream():
        result = crew.switch_mode(name.lower(), cloud_model)
    for agent_name, model in result["changed"].items():
        console.print(f"{agent_name} now uses {model}", markup=False)
    for warning in result["warnings"]:
        console.print(warning, style="yellow", markup=False)
    if result["notice"]:
        console.print(result["notice"], style="cyan", markup=False)
    console.print(f"Mode: {result['mode']}")


@endpoint_app.command("add")
def add_endpoint(
    endpoint_id: str = typer.Argument(..., help="A short id, e.g. lmstudio; its models are then lmstudio:<model>"),
    base_url: str = typer.Argument(..., help="The base URL with /v1, e.g. http://localhost:1234/v1"),
    label: str = typer.Option("", "--label", help="A display name"),
    with_key: bool = typer.Option(False, "--with-key", help="Ask for an API key (stored in the OS keychain)"),
) -> None:
    """Add an OpenAI-compatible endpoint, test it and list its models."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", endpoint_id):
        console.print("The id must be lowercase letters, digits and _, starting with a letter.", style="red")
        raise typer.Exit(1)
    key = typer.prompt("API key", hide_input=True) if with_key else None
    with _upstream():
        catalogue.save_endpoint(endpoint_id, label or endpoint_id, base_url, key.strip() if key else None)
    settings = config.load_settings()
    health = providers.check(endpoint_id, settings.get("endpoints"), privacy=settings["run"]["privacy_mode"])
    console.print(f"{endpoint_id}: {health['status']} {health['detail']}".strip(), markup=False)
    for model_id in health.get("models", []):
        console.print(f"  {endpoint_id}:{model_id}", markup=False)


@endpoint_app.command("rm")
def remove_endpoint(endpoint_id: str = typer.Argument(..., help="The endpoint id")) -> None:
    """Remove a custom endpoint and its key."""
    try:
        with _upstream():
            catalogue.remove_endpoint(endpoint_id)
    except KeyError:
        console.print(f"No endpoint named {endpoint_id}.", style="red", markup=False)
        raise typer.Exit(1) from None
    console.print(f"Removed {endpoint_id}.", markup=False)


# ─── Workspace and sandbox ───────────────────────────────────


def _project_id(project: str) -> str:
    store.init_db()
    return store.find_or_create_project(project)


def _run_id(project_id: str, run_id: int | None) -> int:
    """The given run, which must belong to the project, or its latest run."""
    if run_id is None:
        runs = store.get_runs(project_id)
        if not runs:
            console.print("This project has no runs yet.", style="red")
            raise typer.Exit(1)
        return runs[-1]["id"]
    row = store.get_run(run_id)
    if not row or row["project_id"] != project_id:
        console.print(f"No run {run_id} in this project.", style="red")
        raise typer.Exit(1)
    return run_id


@contextmanager
def _git_errors() -> Iterator[None]:
    try:
        yield
    except workspace.GitError as e:
        console.print(str(e), style="red", markup=False)
        raise typer.Exit(1) from None


@workspace_app.command("tree")
def workspace_tree(project: str = typer.Option("CLI", "--project", help="The project")) -> None:
    """List the files in the project's workspace."""
    project_id = _project_id(project)
    files = workspace.tree(project_id)
    if not files:
        console.print("The workspace is empty.")
        return
    for f in files:
        console.print(f"{f['path']}  [dim]{f['size']:,} B[/]", highlight=False)
    console.print(f"[dim]{workspace.root(project_id)}[/]", highlight=False)


@workspace_app.command("show")
def workspace_show(
    path: str = typer.Argument(..., help="A file in the workspace"), project: str = typer.Option("CLI", "--project")
) -> None:
    """Print one file from the workspace."""
    try:
        f = workspace.read_file(_project_id(project), path)
    except workspace.PathRefused as e:
        console.print(f"That path isn't allowed: {e}", style="red", markup=False)
        raise typer.Exit(1) from None
    except FileNotFoundError:
        console.print(f"No file {path} in the workspace.", style="red", markup=False)
        raise typer.Exit(1) from None
    if f["content"] is None:
        console.print(f"{f['path']} is {'too large' if f['too_large'] else 'binary'} ({f['size']:,} B).", markup=False)
        return
    console.out(f["content"], end="", highlight=False)


@workspace_app.command("diff")
def workspace_diff(
    run: int | None = typer.Option(None, "--run", help="Default: the project's latest run"), project: str = typer.Option("CLI", "--project")
) -> None:
    """Show what a run changed, as a unified diff."""
    run_id = _run_id(_project_id(project), run)
    console.out(workspace.diff(run_id) or f"Run {run_id} wrote no files.\n", end="", highlight=False)


@workspace_app.command("zip")
def workspace_zip(out: str = typer.Argument(..., help="The .zip file to write"), project: str = typer.Option("CLI", "--project")) -> None:
    """Save the workspace (without .git) as a zip file."""
    data = workspace.zip_tree(_project_id(project))
    with open(out, "wb") as f:
        f.write(data)
    console.print(f"Saved {len(data):,} bytes to {out}", highlight=False, markup=False)


@workspace_app.command("commit")
def workspace_commit(
    run: int | None = typer.Option(None, "--run", help="Default: the project's latest run"), project: str = typer.Option("CLI", "--project")
) -> None:
    """Commit the workspace to branch juli/run-<id> (in the workspace's own repo)."""
    project_id = _project_id(project)
    run_id = _run_id(project_id, run)
    row = store.get_run(run_id) or {}
    title = ((row.get("prompt") or "").strip().splitlines() or [""])[0][:72]
    with _git_errors():
        result = workspace.commit(project_id, run_id, f"JULI run {run_id}: {title}")
    console.print(result["detail"] + (f" ({result['commit'][:10]})" if result["commit"] else ""), markup=False)


@workspace_app.command("push")
def workspace_push(
    run: int | None = typer.Option(None, "--run", help="Default: the project's latest run"),
    remote: str | None = typer.Option(None, "--remote", help="https://, ssh:// or git@host:path; saved as origin"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask first"),
    project: str = typer.Option("CLI", "--project"),
) -> None:
    """Push a run's branch (commit it first). Asks before pushing."""
    project_id = _project_id(project)
    run_id = _run_id(project_id, run)
    if remote and workspace.remote_problem(remote):
        console.print(workspace.remote_problem(remote), style="red", markup=False)
        raise typer.Exit(1)
    with _git_errors():
        target = remote or workspace.current_remote(project_id)
    if not target:
        console.print("Say which remote to push to with --remote.", style="red")
        raise typer.Exit(1)
    if not yes and not typer.confirm(f"Push {workspace.branch_name(run_id)} to {target}?", default=False):
        raise typer.Exit(1)
    with _git_errors():
        result = workspace.push(project_id, run_id, remote)
    console.print(f"{result['detail']} to {result['remote']}", markup=False)


@app.command("sandbox")
def sandbox(
    state: str | None = typer.Argument(None, help="on or off; leave out to show the current state"),
    image: str | None = typer.Option(None, "--image", help="The Docker image commands run in"),
    timeout: int | None = typer.Option(None, "--timeout", min=5, max=3600, help="Seconds per command"),
) -> None:
    """Show or set the Docker sandbox for agent commands."""
    from pydantic import ValidationError

    from juli.api.models import SandboxSettings

    if state is not None and state.lower() not in ("on", "off"):
        console.print("Say on or off.", style="red")
        raise typer.Exit(1)
    with config.settings_lock:
        settings = config.load_settings()
        cfg = terminal.sandbox_settings(settings)
        if state is not None or image or timeout:
            enabled = state.lower() == "on" if state else bool(cfg["enabled"])
            try:
                cfg = SandboxSettings(enabled=enabled, image=image or cfg["image"], timeout=timeout or cfg["timeout"]).model_dump()
            except ValidationError:
                console.print("That isn't a valid Docker image name.", style="red")
                raise typer.Exit(1) from None
            settings["sandbox"] = cfg
            config.save_settings(settings)
    problem = terminal.sandbox_problem(cfg)
    console.print(f"Sandbox: {'on' if problem is None else 'off'} · image {cfg['image']} · timeout {cfg['timeout']} s", markup=False)
    if problem:
        console.print(f"Every agent command asks first: {problem}.", style="yellow", markup=False)
    else:
        console.print("Test and lint commands without shell metacharacters run on their own; the rest ask first.")
        console.print(
            f"The image must already have the tools (no network inside). Pull it with `docker pull {cfg['image']}`.", markup=False
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
