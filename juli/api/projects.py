"""Project routes. They touch SQLite, so they are plain `def` (threadpool)."""

from fastapi import APIRouter, HTTPException, Response

from juli import store
from juli.api.models import ProjectCreate
from juli.bus import message_bus

router = APIRouter(prefix="/projects")


def _get_or_404(project_id: str) -> dict:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("")
def list_projects() -> list[dict]:
    return store.get_projects()


@router.post("", status_code=201)
def new_project(payload: ProjectCreate) -> dict:
    return store.create_project(payload.name.strip() or "Untitled Project")


@router.get("/{project_id}")
def fetch_project(project_id: str) -> dict:
    """Project details and its full history."""
    return _get_or_404(project_id)


@router.get("/{project_id}/runs")
def list_runs(project_id: str) -> list[dict]:
    """The project's runs, oldest first, with their totals."""
    if not store.project_exists(project_id):
        raise HTTPException(404, "Project not found")
    return store.get_runs(project_id)


@router.delete("/{project_id}", status_code=204)
def remove_project(project_id: str) -> Response:
    deleted = message_bus.delete_project(project_id, store.delete_project)
    if deleted is None:
        raise HTTPException(409, "A task is running in this project")
    if not deleted:
        raise HTTPException(404, "Project not found")
    return Response(status_code=204)


@router.put("/{project_id}/activate")
def activate_project(project_id: str) -> dict:
    """Make this the project the live view and new messages belong to."""
    if not store.project_exists(project_id):
        raise HTTPException(404, "Project not found")
    if not message_bus.set_active_project(project_id):
        raise HTTPException(409, "A task is running in another project")
    return {"status": "activated", "project_id": project_id}
