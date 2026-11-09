"""
Settings routes. Keys go to the OS keychain; settings.json only records which
providers exist. Responses show key hints ("••••abcd"), never keys.
"""

from fastapi import APIRouter, HTTPException, Response

from juli import config, keystore
from juli.api.models import AgentCreate, AgentUpdates, KeyUpdates, ProviderId

router = APIRouter(prefix="/settings")

KEYCHAIN_HELP = (
    "The OS keychain isn't available on this machine. "
    "Put your keys in a .env file instead (see .env.example), then restart JULI."
)


@router.get("")
def get_settings() -> dict:
    settings = config.load_settings()
    return {
        "agents": settings["agents"],
        "key_hints": {p: keystore.key_hint(keystore.get_key(p)) for p in settings["providers"]},
        "available_models": settings["available_models"],
    }


@router.put("/agents")
def update_agents(agents: AgentUpdates) -> dict:
    with config.settings_lock:
        settings = config.load_settings()
        for name, update in agents.items():
            settings["agents"].setdefault(name, {}).update(update.model_dump(exclude_none=True))
        config.save_settings(settings)
    return {"status": "saved", "count": len(agents)}


@router.post("/agents", status_code=201)
def add_agent(agent: AgentCreate) -> dict:
    with config.settings_lock:
        settings = config.load_settings()
        if agent.name in settings["agents"]:
            raise HTTPException(409, "An agent with this name already exists")
        settings["agents"][agent.name] = {
            "model": agent.model,
            "prompt": agent.prompt or f"You are {agent.name}. Follow instructions precisely.",
            "color": agent.color,
            "icon": agent.icon,
            "job_title": agent.job_title,
        }
        config.save_settings(settings)
    return {"status": "created", "name": agent.name}


@router.delete("/agents/{name}", status_code=204)
def delete_agent(name: str) -> Response:
    with config.settings_lock:
        settings = config.load_settings()
        if name not in settings["agents"]:
            raise HTTPException(404, "Agent not found")
        del settings["agents"][name]
        config.save_settings(settings)
    return Response(status_code=204)


@router.put("/keys")
def update_api_keys(keys: KeyUpdates) -> dict:
    """Store keys in the keychain. Empty or masked ("••••") values are skipped."""
    with config.settings_lock:
        settings = config.load_settings()
        for provider, key in keys.items():
            key = key.strip()
            if key and "•" not in key:
                try:
                    keystore.set_key(provider, key)
                except keystore.KeystoreUnavailable:
                    raise HTTPException(503, KEYCHAIN_HELP) from None
            if provider not in settings["providers"]:
                settings["providers"].append(provider)
        config.save_settings(settings)
    return {"status": "saved"}


@router.delete("/keys/{provider}", status_code=204)
def delete_api_key(provider: ProviderId) -> Response:
    """Remove a provider and delete its key from the keychain."""
    try:
        keystore.delete_key(provider)
    except keystore.KeystoreUnavailable:
        raise HTTPException(503, KEYCHAIN_HELP) from None
    with config.settings_lock:
        settings = config.load_settings()
        if provider in settings["providers"]:
            settings["providers"].remove(provider)
            config.save_settings(settings)
    return Response(status_code=204)
