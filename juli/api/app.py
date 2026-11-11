"""
JULI: FastAPI app factory.

Run with `uvicorn --factory juli.api.app:create_app`, or `juli serve`, which
also serves the built dashboard on the same origin. Every /api route except
GET /api/health needs `Authorization: Bearer <token>`. The WebSockets at /ws
(live agent messages) and /ws/terminal (the IDE terminal) need an allowed
Origin and the token in their first message.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from juli import __version__, config, data, store
from juli.api import data as data_routes
from juli.api import local, projects, providers, security, settings, tasks, workspace
from juli.bus import AgentMessage, message_bus

log = logging.getLogger(__name__)

# Seconds a WebSocket client has to send its auth message.
WS_AUTH_TIMEOUT = 5.0


class ConnectionManager:
    """Authenticated WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    def add(self, websocket: WebSocket) -> None:
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001 - one broken socket must never stop the broadcast
                self.disconnect(connection)


async def greet(websocket: WebSocket) -> dict | None:
    """Accept, check Origin, and read the first message, which must carry the
    token within WS_AUTH_TIMEOUT. Returns it, or None once the socket is closed."""
    # Accept before refusing, so browsers see the close code (a refused
    # handshake surfaces only as 1006) and the client stops reconnecting.
    await websocket.accept()
    if not security.origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=4403)
        return None
    try:
        hello = await asyncio.wait_for(websocket.receive_json(), WS_AUTH_TIMEOUT)
    except (TimeoutError, ValueError, WebSocketDisconnect):
        hello = None
    if not (isinstance(hello, dict) and security.token_matches(websocket.app.state.token, hello.get("token"))):
        await websocket.close(code=4401)
        return None
    return hello


async def message_bridge(manager: ConnectionManager) -> None:
    """Forward bus messages to every connected WebSocket client."""
    queue = message_bus.subscribe_async()
    try:
        while True:
            msg: AgentMessage = await queue.get()
            await manager.broadcast(msg.to_dict())
    finally:
        message_bus.unsubscribe_async(queue)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    config.migrate_legacy_settings()
    try:
        data.apply_retention()
    except Exception:
        log.exception("Applying the retention period failed; JULI starts anyway")
    message_bus.set_persister(store.save_message)
    task = asyncio.create_task(message_bridge(app.state.connections))
    yield
    for session in list(app.state.terminals):
        session.close()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    message_bus.set_persister(None)


def create_app(token: str | None = None, static_dir: Path | None = None, port: int = 8000) -> FastAPI:
    """The app. With static_dir (the built dashboard, frontend/dist), it also
    serves the dashboard at / on `port`, so browser and API share one origin."""
    token = token or os.environ.get("JULI_TOKEN")
    if not token:
        # Never generate-and-print: the token would end up in terminal logs.
        raise RuntimeError("JULI_TOKEN is not set. Start JULI with `python run.py`, which creates one.")

    debug = os.environ.get("JULI_DEBUG") == "1"
    app = FastAPI(
        title="JULI",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if debug else None,
    )
    app.state.token = token
    app.state.connections = ConnectionManager()
    app.state.limiter = security.RateLimiter()
    app.state.terminals = set()  # open PTY sessions

    # The last middleware added runs first: headers wrap everything, 429s included.
    app.middleware("http")(app.state.limiter.middleware)
    app.middleware("http")(security.security_headers)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    auth = [Depends(security.require_token)]
    for module in (tasks, projects, settings, providers, local, workspace, data_routes):
        app.include_router(module.router, prefix="/api", dependencies=auth)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Live agent messages. First message must be {"type":"auth","token":...}."""
        hello = await greet(websocket)
        if hello is None:
            return
        if hello.get("type") != "auth":
            await websocket.close(code=4401)
            return

        manager: ConnectionManager = app.state.connections
        await websocket.send_json(
            AgentMessage(
                agent_name="System",
                content=f"Connected to JULI — Status: {message_bus.task_status}",
                message_type="status",
                data={"status": message_bus.task_status},
                run_id=message_bus.active_run_id,
            ).to_dict()
        )
        for msg in message_bus.history:
            await websocket.send_json(msg.to_dict())
        manager.add(websocket)
        try:
            while True:
                await websocket.receive_text()  # tasks start via REST only
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(websocket)

    @app.websocket("/ws/terminal")
    async def terminal_endpoint(websocket: WebSocket) -> None:
        """The user's shell in a project's workspace. First message: {token, project_id, cols, rows}."""
        hello = await greet(websocket)
        if hello is not None:
            await workspace.terminal_socket(websocket, hello)

    if static_dir is not None:
        serve_dashboard(app, static_dir, port)
    return app


def serve_dashboard(app: FastAPI, static_dir: Path, port: int) -> None:
    """The built dashboard: index.html at /, hashed bundles at /assets, the mascot at /mascot."""
    index, assets = static_dir / "index.html", static_dir / "assets"
    missing = [str(p) for p, ok in ((index, index.is_file()), (assets, assets.is_dir())) if not ok]
    if missing:
        raise RuntimeError(f"The dashboard isn't built: {' and '.join(missing)} missing. Run `npm run build` in frontend/.")
    app.state.ui_csp = security.ui_csp(port)
    app.mount("/assets", StaticFiles(directory=assets), name="assets")
    if (static_dir / "mascot").is_dir():
        app.mount("/mascot", StaticFiles(directory=static_dir / "mascot"), name="mascot")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def dashboard() -> FileResponse:
        # Always revalidate the page; the bundles it names are content-hashed.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
