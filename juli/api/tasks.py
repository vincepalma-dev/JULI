"""Task routes: start a task, read status and the live message view."""

import logging
import threading
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from juli import store
from juli.api.models import (
    AgentInfo,
    AgentMessageResponse,
    TaskRequest,
    TaskStatusResponse,
)
from juli.bus import message_bus

log = logging.getLogger(__name__)
router = APIRouter()


def _run(run_task: Callable, run_id: int, request: TaskRequest) -> None:
    try:
        run_task(
            prompt=request.prompt,
            mode=request.mode,
            max_round=request.max_round,
            no_devops=request.no_devops,
        )
    except Exception:
        log.exception("Task failed")
        message_bus.set_task_status("error")
    finally:
        if message_bus.task_status == "running":
            message_bus.set_task_status("complete")
        store.finish_run(run_id, message_bus.task_status)


@router.post("/task", status_code=202)
def start_task(request: TaskRequest) -> dict:
    """Start a task in a background thread. Each task gets a new run row."""
    if not store.project_exists(request.project_id):
        raise HTTPException(404, "Project not found")
    try:
        # Imported here so the API (and its tests) load without pyautogen.
        from agents.orchestrator import run_task
    except ImportError as e:
        raise HTTPException(503, f"The agent engine can't load: {e}. Install requirements.txt.") from None

    if not message_bus.try_begin_task(request.prompt, request.project_id):
        raise HTTPException(409, "A task is already running")
    try:
        run_id = store.create_run(request.project_id, request.prompt, request.mode)
    except Exception:
        message_bus.set_task_status("error")
        raise
    message_bus.start_run(request.project_id, run_id)

    threading.Thread(target=_run, args=(run_task, run_id, request), daemon=True).start()
    return {"status": "started", "run_id": run_id, "mode": request.mode}


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
    from agents.agents import AGENT_INFO

    return AGENT_INFO
