"""
Workspace routes: a project's file tree, one file and a zip; a run's files
and diff; commit to juli/run-<id> and push (which asks first); the Docker
sandbox settings. Also the /ws/terminal handler: the user's own shell in the
project's workspace.
"""

import asyncio
import json
import threading
from typing import Annotated

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)

from juli import config, store, terminal, workspace
from juli.api.models import PushRequest, SandboxSettings
from juli.api.security import TERMINAL_LIMIT
from juli.bus import BUSY, message_bus

router = APIRouter()

MAX_TERMINALS = 8
MAX_INPUT_CHARS = 65_536
# Output chunks read from a PTY but not yet sent; the reader waits beyond this.
TERMINAL_BACKLOG = 256


def _require_project(project_id: str) -> None:
    if not workspace.PROJECT_ID.match(project_id) or not store.project_exists(project_id):
        raise HTTPException(404, "Project not found")


def _require_run(run_id: int) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


def _busy_in(project_id: str) -> bool:
    return message_bus.task_status in BUSY and message_bus.active_project_id == project_id


@router.get("/projects/{project_id}/workspace/tree")
def get_tree(project_id: str) -> dict:
    """Every file in the project's workspace (except .git), with sizes."""
    _require_project(project_id)
    return {"files": workspace.tree(project_id)}


@router.get("/projects/{project_id}/workspace/file")
def get_file(project_id: str, path: Annotated[str, Query(min_length=1, max_length=workspace.MAX_PATH)]) -> dict:
    """One file. Binary or very large files come back without their content."""
    _require_project(project_id)
    try:
        return workspace.read_file(project_id, path)
    except workspace.PathRefused as e:
        raise HTTPException(422, f"That path isn't allowed: {e}") from None
    except FileNotFoundError:
        raise HTTPException(404, "File not found") from None


@router.get("/projects/{project_id}/workspace/zip")
def get_zip(project_id: str) -> Response:
    """The workspace as a zip, without .git."""
    _require_project(project_id)
    return Response(
        workspace.zip_tree(project_id),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="juli-{project_id[:8]}.zip"'},
    )


@router.get("/runs/{run_id}/files")
def run_files(run_id: int) -> list[dict]:
    """The files a run wrote, each added or modified."""
    _require_run(run_id)
    return [{"path": f["path"], "status": "added" if f["before_text"] is None else "modified"} for f in store.run_files(run_id)]


@router.get("/runs/{run_id}/diff")
def run_diff(run_id: int) -> dict:
    """A unified diff of the run's files, from before the run to its last write."""
    _require_run(run_id)
    return {"diff": workspace.diff(run_id)}


@router.post("/runs/{run_id}/commit")
def commit_run(run_id: int) -> dict:
    """Commit the workspace to branch juli/run-<id>."""
    run = _require_run(run_id)
    if _busy_in(run["project_id"]):
        raise HTTPException(409, "A task is running in this project; commit when it's done")
    title = (run["prompt"].strip().splitlines() or [""])[0][:72]
    try:
        return workspace.commit(run["project_id"], run_id, f"JULI run {run_id}: {title}")
    except workspace.GitError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/runs/{run_id}/push")
def push_run(run_id: int, body: PushRequest) -> dict:
    """Push branch juli/run-<id>. Without confirm, nothing is pushed: a 409
    says what would be, so the user can agree first."""
    run = _require_run(run_id)
    project_id = run["project_id"]
    if body.remote:
        problem = workspace.remote_problem(body.remote)
        if problem:
            raise HTTPException(422, problem)
    try:
        remote = body.remote or workspace.current_remote(project_id)
        if not remote:
            raise HTTPException(409, "Say which remote to push to")
        branch = workspace.branch_name(run_id)
        if not body.confirm:
            raise HTTPException(
                409,
                {"message": f"Push {branch} to {remote}?", "confirm": {"branch": branch, "remote": remote}},
            )
        return workspace.push(project_id, run_id, body.remote)
    except workspace.GitError as e:
        raise HTTPException(409, str(e)) from None


@router.get("/sandbox")
def get_sandbox() -> dict:
    """The sandbox settings, and why it's off when it is."""
    cfg = terminal.sandbox_settings(config.load_settings())
    problem = terminal.sandbox_problem(cfg)
    return {"settings": cfg, "active": problem is None, "problem": problem}


@router.put("/sandbox")
def put_sandbox(body: SandboxSettings) -> dict:
    with config.settings_lock:
        settings = config.load_settings()
        settings["sandbox"] = body.model_dump()
        config.save_settings(settings)
    return get_sandbox()


# ─── Terminal ────────────────────────────────────────────────


def _size_ok(cols: object, rows: object) -> bool:
    return (
        isinstance(cols, int) and not isinstance(cols, bool) and 1 <= cols <= 500
        and isinstance(rows, int) and not isinstance(rows, bool) and 1 <= rows <= 200
    )  # fmt: skip


def _open_terminal(project_id: str, cols: int, rows: int) -> terminal.PtySession:
    return terminal.PtySession(workspace.ensure(project_id), cols, rows)


async def terminal_socket(websocket: WebSocket, hello: dict) -> None:
    """Serve one authenticated terminal. Client messages: {"type":"input","data"}
    and {"type":"resize","cols","rows"}. Server messages: {"type":"output","data"},
    then {"type":"exit"} when the shell ends."""
    state = websocket.app.state
    project_id, cols, rows = hello.get("project_id"), hello.get("cols"), hello.get("rows")
    if not (isinstance(project_id, str) and workspace.PROJECT_ID.match(project_id) and _size_ok(cols, rows)):
        await websocket.close(code=4400)
        return
    if not await asyncio.to_thread(store.project_exists, project_id):
        await websocket.close(code=4404)
        return
    client = websocket.client.host if websocket.client else "unknown"
    if len(state.terminals) >= MAX_TERMINALS or state.limiter.check((client, "terminal"), TERMINAL_LIMIT) > 0:
        await websocket.close(code=4429)
        return
    try:
        session = await asyncio.to_thread(_open_terminal, project_id, int(cols), int(rows))  # type: ignore[arg-type]  # checked by _size_ok
    except terminal.TerminalUnavailable as e:
        await websocket.close(code=4503, reason=str(e)[:120])
        return

    state.terminals.add(session)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    slots = threading.BoundedSemaphore(TERMINAL_BACKLOG)
    closed = threading.Event()

    def forward(data: str | None) -> None:
        """On the reader thread: wait for room, then hand the chunk to the loop."""
        if data is not None:
            while not slots.acquire(timeout=0.5):
                if closed.is_set():
                    return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, data)
        except RuntimeError:  # the loop is gone
            pass

    async def send_output() -> None:
        while True:
            data = await queue.get()
            if data is None:
                await websocket.send_json({"type": "exit"})
                await websocket.close(code=1000)
                return
            slots.release()
            await websocket.send_json({"type": "output", "data": data})

    async def read_input() -> None:
        while True:
            try:
                msg = json.loads(await websocket.receive_text())
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "input" and isinstance(msg.get("data"), str) and len(msg["data"]) <= MAX_INPUT_CHARS:
                await asyncio.to_thread(session.write, msg["data"])
            elif msg.get("type") == "resize" and _size_ok(msg.get("cols"), msg.get("rows")):
                await asyncio.to_thread(session.resize, msg["cols"], msg["rows"])

    session.start(forward)
    tasks = [asyncio.create_task(send_output()), asyncio.create_task(read_input())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        closed.set()
        # Close the PTY on a thread, started before anything else is awaited, and
        # keep the session counted until it's gone. The discard runs when the close
        # finishes, so a cleanup cut short by cancellation (the client left, the
        # server is stopping) still closes the shell and still unregisters it.
        closing = asyncio.ensure_future(asyncio.to_thread(session.close))
        closing.add_done_callback(lambda _: state.terminals.discard(session))
        for task in tasks:
            task.cancel()
            # Retrieve each task's exception (e.g. the client's disconnect), so
            # asyncio doesn't report it as never retrieved.
            task.add_done_callback(lambda t: t.cancelled() or t.exception())
        # asyncio.wait, not gather: on Python 3.10, a cancellation that arrives
        # while awaiting gather loses its message, so the server (or a test
        # client) can't tell it's the cancellation it asked for and lets it escape.
        await asyncio.wait(tasks)
        await asyncio.shield(closing)
