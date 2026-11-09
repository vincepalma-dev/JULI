"""
JULI — FastAPI Backend Server.
Provides REST API endpoints and WebSocket streaming for the multi-agent dashboard.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any

from backend.models import (
    TaskRequest,
    AgentMessageResponse,
    TaskStatusResponse,
    AgentInfo,
)
from agents.message_bus import message_bus, AgentMessage
from agents.orchestrator import run_task_async, get_agent_info
from agents.agents import SYSTEM_PROMPTS, AGENT_COLORS, AGENT_ICONS
import backend.projects_db as projects_db


# ─────────────────────────────────────────────────────────────
# Settings Persistence
# ─────────────────────────────────────────────────────────────

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"

DEFAULT_MODELS = ["gpt4", "claude", "gemini", "gemini_flash"]

DEFAULT_AGENT_MODEL_MAP = {
    "PlannerResearcher": "gpt4",
    "Coder": "claude",
    "ReviewerSecurity": "gpt4",
    "DevOps": "gemini",
    "TestMonitor": "gemini",
    "DocsDiagram": "gemini_flash",
}

DEFAULT_AGENT_ICONS = {
    "PlannerResearcher": "planner",
    "Coder": "coder",
    "ReviewerSecurity": "reviewer",
    "DevOps": "devops",
    "TestMonitor": "test",
    "DocsDiagram": "docs",
}


def load_settings() -> dict:
    """Load settings from JSON file, or return defaults."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "agents": {
            name: {
                "model": DEFAULT_AGENT_MODEL_MAP.get(name, "gpt4"),
                "prompt": prompt,
                "color": AGENT_COLORS.get(name, "#6b7280"),
                "icon": DEFAULT_AGENT_ICONS.get(name, "system"),
                "job_title": f"{name} Specialist",
            }
            for name, prompt in SYSTEM_PROMPTS.items()
        },
        "api_keys": {
            "openai": os.environ.get("OPENAI_API_KEY", ""),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "google": os.environ.get("GOOGLE_API_KEY", ""),
        },
        "available_models": DEFAULT_MODELS,
    }


def save_settings(settings: dict):
    """Persist settings to JSON file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ─────────────────────────────────────────────────────────────
# WebSocket Connection Manager
# ─────────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ─────────────────────────────────────────────────────────────
# Background task: bridge message_bus → WebSocket clients
# ─────────────────────────────────────────────────────────────

async def message_bridge():
    """Continuously reads from the message bus and broadcasts to WebSocket clients."""
    queue = message_bus.subscribe_async()
    try:
        while True:
            msg: AgentMessage = await queue.get()
            await manager.broadcast(msg.to_dict())
    except asyncio.CancelledError:
        message_bus.unsubscribe_async(queue)


# ─────────────────────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the message bridge background task."""
    task = asyncio.create_task(message_bridge())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="JULI",
    description="Real-time monitoring dashboard for the AutoGen multi-agent system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow Vue dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# REST Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"name": "JULI", "status": "online", "version": "1.0.0"}


@app.post("/api/task", response_model=dict)
async def start_task(request: TaskRequest):
    """Start a new AutoGen task in the background."""
    if message_bus.task_status == "running":
        return {"error": "A task is already running", "status": "rejected"}

    message_bus.clear_history()

    # Run the task in a background thread
    run_task_async(
        prompt=request.prompt,
        mode=request.mode,
        max_round=request.max_round,
        no_devops=request.no_devops,
    )

    return {"status": "started", "prompt": request.prompt, "mode": request.mode}


@app.get("/api/status", response_model=TaskStatusResponse)
async def get_status():
    """Get current task status."""
    return TaskStatusResponse(
        status=message_bus.task_status,
        current_task=message_bus.current_task,
        message_count=len(message_bus.history),
    )


@app.get("/api/messages", response_model=List[AgentMessageResponse])
async def get_messages():
    """Get all messages from the current/last task."""
    return [
        AgentMessageResponse(
            agent_name=msg.agent_name,
            content=msg.content,
            timestamp=msg.timestamp,
            message_type=msg.message_type,
        )
        for msg in message_bus.history
    ]


@app.get("/api/agents", response_model=List[AgentInfo])
async def get_agents():
    """Get metadata about all available agents."""
    return [AgentInfo(**info) for info in get_agent_info()]


# ─────────────────────────────────────────────────────────────
# Projects Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    """List all available projects."""
    return projects_db.get_projects()

@app.post("/api/projects")
async def new_project(payload: dict):
    """Create a new project."""
    name = payload.get("name", "Untitled Project")
    return projects_db.create_project(name)

@app.get("/api/projects/{project_id}")
async def fetch_project(project_id: str):
    """Get project details and history."""
    p = projects_db.get_project(project_id)
    if not p:
        return {"error": "Project not found"}
    return p

@app.delete("/api/projects/{project_id}")
async def remove_project(project_id: str):
    """Delete a project."""
    success = projects_db.delete_project(project_id)
    return {"status": "deleted" if success else "not found"}

@app.put("/api/projects/{project_id}/activate")
async def activate_project(project_id: str):
    """Switch the active project context for the message bus."""
    p = projects_db.get_project(project_id)
    if not p:
        return {"error": "Project not found"}
    message_bus.set_active_project(project_id)
    return {"status": "activated", "project_id": project_id}


# ─────────────────────────────────────────────────────────────
# Settings Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    """Get all settings (agents, models, api keys)."""
    settings = load_settings()
    # Mask API keys for security
    masked_keys = {}
    for provider, key in settings.get("api_keys", {}).items():
        if key and len(str(key)) > 8:
            key_str = str(key)
            masked_keys[provider] = key_str[:4] + "•" * (len(key_str) - 8) + key_str[-4:]
        elif key:
            masked_keys[provider] = "•" * len(key)
        else:
            masked_keys[provider] = ""
    return {
        "agents": settings.get("agents", {}),
        "api_keys": masked_keys,
        "available_models": settings.get("available_models", DEFAULT_MODELS),
    }


@app.put("/api/settings/agents")
async def update_agents(agents: Dict[str, Any]):
    """Update agent configurations (model, prompt, color, icon)."""
    settings = load_settings()
    for name, config in agents.items():
        if name not in settings["agents"]:
            settings["agents"][name] = {}
        settings["agents"][name].update(config)
    save_settings(settings)
    return {"status": "saved", "count": len(agents)}


@app.post("/api/settings/agents")
async def add_agent(agent: Dict[str, Any]):
    """Add a new custom agent."""
    name = agent.get("name", "").strip()
    if not name:
        return {"error": "Agent name is required"}
    settings = load_settings()
    settings["agents"][name] = {
        "model": agent.get("model", "gpt4"),
        "prompt": agent.get("prompt", f"You are {name}. Follow instructions precisely."),
        "color": agent.get("color", "#6b7280"),
        "icon": agent.get("icon", "system"),
        "job_title": agent.get("job_title", ""),
    }
    save_settings(settings)
    return {"status": "created", "name": name}


@app.delete("/api/settings/agents/{name}")
async def delete_agent(name: str):
    """Delete a custom agent."""
    settings = load_settings()
    if name in settings.get("agents", {}):
        del settings["agents"][name]
        save_settings(settings)
        return {"status": "deleted", "name": name}
    return {"error": "Agent not found"}


@app.put("/api/settings/keys")
async def update_api_keys(keys: Dict[str, str]):
    """Update API keys. Only non-masked values are saved."""
    settings = load_settings()
    for provider, key in keys.items():
        # Don't overwrite with masked values
        if key and "•" not in key:
            settings["api_keys"][provider] = key
            # Also set as environment variable for the current session
            env_map = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY"}
            if provider in env_map:
                os.environ[env_map[provider]] = key
    save_settings(settings)
    return {"status": "saved"}


# ─────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent message streaming.
    Clients connect here to receive live updates.
    """
    await manager.connect(websocket)

    # Send current status on connect
    await websocket.send_json({
        "agent_name": "System",
        "content": f"Connected to JULI — Status: {message_bus.task_status}",
        "timestamp": "",
        "message_type": "status",
    })

    # Send history on connect
    for msg in message_bus.history:
        await websocket.send_json(msg.to_dict())

    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await websocket.receive_text()
            # Client can send task requests via WebSocket too
            try:
                payload = json.loads(data)
                if payload.get("type") == "start_task":
                    if message_bus.task_status != "running":
                        message_bus.clear_history()
                        run_task_async(
                            prompt=payload.get("prompt", ""),
                            mode=payload.get("mode", "full"),
                        )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

