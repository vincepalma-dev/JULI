"""Task routes: start, stop, steer and answer a task; follow-up chat; status and the live view."""

import logging
import threading

from fastapi import APIRouter, HTTPException

from juli import config, store
from juli.api.models import (
    AgentInfo,
    AgentMessageResponse,
    Decision,
    FollowUp,
    TaskNote,
    TaskRequest,
    TaskStatusResponse,
)
from juli.bus import message_bus

log = logging.getLogger(__name__)
router = APIRouter()


def _run(engine, run, run_id: int) -> None:
    result = engine.RunResult("error")
    try:
        result = engine.execute(run)
    except Exception:
        log.exception("Task failed")
        message_bus.set_task_status("error")
    finally:
        store.finish_run(run_id, result.status, result.tokens_in, result.tokens_out, result.cost_usd)


@router.post("/task", status_code=202)
def start_task(request: TaskRequest) -> dict:
    """Start a task in a background thread. Each task gets a new run row."""
    if not store.project_exists(request.project_id):
        raise HTTPException(404, "Project not found")
    # Imported here so the API loads without the engine and its providers.
    from juli import engine

    settings = config.load_settings()
    run = engine.Run(
        request.prompt,
        request.mode,
        engine.build_crew(settings),
        settings=settings,
        max_cycles=request.max_cycles,
        approve_plan=request.approve_plan,
        discussion_rounds=request.discussion_rounds,
        no_devops=request.no_devops,
        review_source=engine.review_source(request.project_id) if request.mode == "review" else "",
    )
    warnings, blocked = engine.allowance_report(run.agents, settings)
    if blocked and not request.ignore_allowance:
        raise HTTPException(409, "Monthly allowance reached: " + "; ".join(blocked) + ". Start with ignore_allowance to continue.")
    run.notices = warnings + blocked

    run_id = engine.begin(request.project_id, run)
    if run_id is None:
        raise HTTPException(409, "A task is already running")
    threading.Thread(target=_run, args=(engine, run, run_id), daemon=True).start()
    return {"status": "started", "run_id": run_id, "mode": request.mode}


@router.post("/task/stop")
def stop_task() -> dict:
    """Stop the running task. Its partial output is kept."""
    from juli import engine

    if not engine.stop():
        raise HTTPException(409, "No task is running")
    return {"status": "stopping"}


@router.post("/task/decision")
def decide(decision: Decision) -> dict:
    """Answer a paused task: approve or revise the plan, switch model and resume, or stop."""
    from juli import engine

    error = engine.decide(decision.action, decision.model, decision.message)
    if error:
        raise HTTPException(409, error)
    return {"status": "accepted"}


@router.post("/task/message")
def send_note(note: TaskNote) -> dict:
    """Tell the running crew something. Every later agent turn sees it."""
    from juli import engine

    if not engine.say(note.content):
        raise HTTPException(409, "No task is running")
    return {"status": "sent"}


@router.post("/runs/{run_id}/chat")
def follow_up(run_id: int, body: FollowUp) -> dict:
    """Ask one agent a question about a finished run."""
    from juli import engine, providers

    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if not run["ended_at"]:
        raise HTTPException(409, "This run is still going. Send the crew a message instead.")
    settings = config.load_settings()
    if body.agent not in settings["agents"]:
        raise HTTPException(404, "Agent not found")
    agent = [a for a in engine.build_crew(settings) if a.name == body.agent]
    _, blocked = engine.allowance_report(agent, settings)
    if blocked and not body.ignore_allowance:
        raise HTTPException(409, "Monthly allowance reached: " + "; ".join(blocked))
    try:
        return engine.follow_up(run, body.agent, body.message, settings)
    except providers.PrivacyViolation as e:
        raise HTTPException(409, str(e)) from None
    except providers.ProviderError as e:
        raise HTTPException(502, providers.redact(str(e))) from None


@router.get("/status", response_model=TaskStatusResponse)
def get_status() -> TaskStatusResponse:
    return TaskStatusResponse(
        status=message_bus.task_status,
        current_task=message_bus.current_task,
        message_count=len(message_bus.history),
    )


@router.get("/messages", response_model=list[AgentMessageResponse])
def get_messages() -> list:
    """Messages in the live view (the current or last task)."""
    return [msg.to_dict() for msg in message_bus.history]


@router.get("/agents", response_model=list[AgentInfo])
def get_agents() -> list:
    """The crew from settings."""
    from juli import roles

    return [
        {
            "name": name,
            "role": roles.role_of(name, cfg),
            "color": cfg.get("color", "#6b7280"),
            "icon": cfg.get("icon", "system"),
            "model": cfg.get("model", ""),
        }
        for name, cfg in config.load_settings()["agents"].items()
    ]
