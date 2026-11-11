"""
Settings routes. Keys go to the OS keychain; settings.json only records which
providers exist. Responses show key hints ("••••abcd"), never keys.
"""

from fastapi import APIRouter, HTTPException, Response

from juli import config, keystore, roles
from juli import providers as llm
from juli.api.models import AgentCreate, AgentUpdates, KeyUpdates, ModeRequest, ProviderId, RunSettings
from juli.local import crew

router = APIRouter(prefix="/settings")

KEYCHAIN_HELP = (
    "The OS keychain isn't available on this machine. Put your keys in a .env file instead (see .env.example), then restart JULI."
)


def _require_known_provider(model: str, settings: dict) -> None:
    provider = model.partition(":")[0]
    if llm.provider_info(provider, settings.get("endpoints")) is None:
        raise HTTPException(422, f"Unknown provider '{provider}' in model '{model}'")


@router.get("")
def get_settings() -> dict:
    settings = config.load_settings()
    in_use = [a.get("model") for a in settings["agents"].values() if isinstance(a, dict) and a.get("model")]
    # Each agent with its effective role: older settings leave it to the name.
    agents = {name: {**cfg, "role": roles.role_of(name, cfg)} for name, cfg in settings["agents"].items() if isinstance(cfg, dict)}
    return {
        "agents": agents,
        "key_hints": {p: keystore.key_hint(keystore.get_key(p)) for p in settings["providers"]},
        "available_models": list(dict.fromkeys(llm.preset_refs() + settings["available_models"] + in_use)),
        "run": settings["run"],
        "mode": crew.current_mode(settings),
    }


@router.put("/agents")
def update_agents(agents: AgentUpdates) -> dict:
    with config.settings_lock:
        settings = config.load_settings()
        for name, update in agents.items():
            # Unset fields stay as they are; an explicit null only clears max_tokens.
            changes = {k: v for k, v in update.model_dump(exclude_unset=True).items() if v is not None or k == "max_tokens"}
            agent = settings["agents"].setdefault(name, {})
            if changes.get("model"):
                _require_known_provider(changes["model"], settings)
                if changes["model"] != agent.get("model"):
                    agent.pop("num_ctx", None)  # fitted to the old model; Auto-Crew sets it again
            agent.update(changes)
        config.save_settings(settings)
    return {"status": "saved", "count": len(agents)}


@router.post("/agents", status_code=201)
def add_agent(agent: AgentCreate) -> dict:
    with config.settings_lock:
        settings = config.load_settings()
        if agent.name in settings["agents"]:
            raise HTTPException(409, "An agent with this name already exists")
        _require_known_provider(agent.model, settings)
        settings["agents"][agent.name] = {
            "role": agent.role,
            "model": agent.model,
            "prompt": agent.prompt or f"You are {agent.name}. Follow instructions precisely.",
            "color": agent.color,
            "icon": agent.icon,
            "job_title": agent.job_title,
            "max_tokens": agent.max_tokens,
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


@router.put("/run")
def update_run_settings(run: RunSettings) -> dict:
    """Budget cap, token cap, Privacy Mode, local fallback and monthly allowances."""
    with config.settings_lock:
        settings = config.load_settings()
        if run.fallback_model:
            _require_known_provider(run.fallback_model, settings)
            if not llm.is_local(run.fallback_model, settings.get("endpoints")):
                raise HTTPException(422, "The fallback model must run locally")
        settings["run"] = run.model_dump()
        config.save_settings(settings)
    return {"status": "saved", "run": settings["run"]}


@router.get("/mode")
def get_mode() -> dict:
    """privacy, hybrid, cloud, or custom when the crew matches none of them."""
    return {"mode": crew.current_mode(config.load_settings())}


@router.put("/mode")
def set_mode(body: ModeRequest) -> dict:
    """Switch the crew to Privacy, Hybrid or Cloud mode.

    Only agents in the wrong place move: local ones get an Auto-Crew pick,
    cloud ones get cloud_model. The notice says what goes to which provider.
    """
    try:
        return crew.switch_mode(body.mode, body.cloud_model)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.put("/keys")
def update_api_keys(keys: KeyUpdates) -> dict:
    """Store keys in the keychain, then health-check each saved key.

    Empty or masked ("••••") values are skipped.
    """
    saved = []
    with config.settings_lock:
        settings = config.load_settings()
        for provider, key in keys.items():
            key = key.strip()
            if key and "•" not in key:
                try:
                    keystore.set_key(provider, key)
                except keystore.KeystoreUnavailable:
                    raise HTTPException(503, KEYCHAIN_HELP) from None
                saved.append(provider)
            if provider not in settings["providers"]:
                settings["providers"].append(provider)
        config.save_settings(settings)
    # Network checks run outside the settings lock.
    health = {p: llm.check(p, settings.get("endpoints"), privacy=settings["run"]["privacy_mode"]) for p in saved}
    return {"status": "saved", "health": health}


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
