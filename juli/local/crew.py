"""
Auto-Crew and the Privacy / Hybrid / Cloud modes.

Agents run one at a time, so each role's model only has to fit on its own.
Auto-Crew picks, per role, the strongest catalogue model (most parameters)
whose roles match, in the great tier, else slow; ties go to installed models.
A role with no matching model that fits gets the best general model. If the
downloads don't fit on disk together, every role shares one model. It only
changes the agents it's asked to change.

The modes aren't a separate setting. Privacy is run.privacy_mode, enforced in
providers.stream. Hybrid (Plan and Review in the cloud, the rest local) and
Cloud describe where the crew's models run; current_mode() reads that back.
"""

from collections.abc import Callable, Mapping

from juli import config, keystore, providers, roles
from juli.local import catalogue, hardware, ollama

# Crew roles mapped to catalogue roles. Custom agents get general models.
CATALOGUE_ROLE = {"planner": "planner", "coder": "coder", "reviewer": "reviewer", "tester": "tester", "docs": "docs"}
TIERS = {"great": 2, "slow": 1}
CLOUD_ROLES = ("planner", "reviewer")  # in the cloud in Hybrid mode
MODES = ("privacy", "hybrid", "cloud")


# ─── Auto-Crew (pure) ────────────────────────────────────────


def _rate(hw: dict, installed: set[str]) -> list[dict]:
    return [{"entry": m, "installed": m["tag"] in installed, "fit": hardware.fit(m, hw, m["tag"] in installed)} for m in catalogue.MODELS]


def _best(rated: list[dict], role: str) -> dict | None:
    fitting = [r for r in rated if role in r["entry"]["roles"] and r["fit"]["tier"] in TIERS]
    return max(fitting, key=lambda r: (TIERS[r["fit"]["tier"]], r["entry"]["params_b"], r["installed"]), default=None)


def _pick(rated: dict) -> dict:
    return {
        "model": "ollama:" + rated["entry"]["tag"],
        "num_ctx": rated["fit"]["num_ctx"],
        "tier": rated["fit"]["tier"],
        "installed": rated["installed"],
        "size_gb": rated["entry"]["size_gb"],
    }


def auto_crew(hw: dict, installed: set[str], agents: Mapping[str, str]) -> dict:
    """Model picks for the given agents (name -> crew role)."""
    rated = _rate(hw, installed)
    general = _best(rated, "general")
    chosen = {name: _best(rated, CATALOGUE_ROLE.get(role, "general")) or general for name, role in agents.items()}

    def downloads(picks: dict) -> dict[str, float]:
        return {r["entry"]["tag"]: r["entry"]["size_gb"] for r in picks.values() if r and not r["installed"]}

    shared = False
    free = hw.get("disk_free_gb")
    if free is not None and general and sum(downloads(chosen).values()) > free:
        chosen = {name: general for name in agents}
        shared = True
    needed = downloads(chosen)
    return {
        "agents": {name: _pick(r) if r else None for name, r in chosen.items()},
        "downloads": sorted(needed),
        "download_gb": round(sum(needed.values()), 1),
        "shared": shared,
        "fallback_model": _pick(general)["model"] if general else None,
        "warnings": [f"No catalogue model fits this machine for {name}" for name, r in chosen.items() if r is None],
    }


def apply_picks(settings: dict, picks: Mapping[str, dict | None]) -> list[str]:
    """Write picked models and num_ctx into settings agents. Returns the names changed."""
    changed = []
    for name, pick in picks.items():
        agent = settings["agents"].get(name)
        if pick and isinstance(agent, dict):
            agent["model"], agent["num_ctx"] = pick["model"], pick["num_ctx"]
            changed.append(name)
    return changed


def crew_roles(settings: dict, names: list[str] | None = None) -> dict[str, str]:
    """name -> role for the named agents (all when names is None)."""
    agents = {n: c for n, c in settings["agents"].items() if isinstance(c, dict)}
    unknown = [n for n in names or [] if n not in agents]
    if unknown:
        raise ValueError(f"No agent named {', '.join(unknown)}")
    return {name: roles.role_of(name, cfg) for name, cfg in agents.items() if names is None or name in names}


def run_auto_crew(names: list[str] | None = None, apply: bool = False, set_fallback: bool = False) -> dict:
    """Pick models for this machine and, if asked, save them.

    set_fallback also makes the best general model the run's local fallback.
    licenses lists what must be accepted before the downloads.
    """
    settings = config.load_settings()
    hw = hardware.current()
    result = auto_crew(hw, ollama.installed(settings.get("endpoints")), crew_roles(settings, names))
    needed = [catalogue.license_needed(tag, settings) for tag in result["downloads"]]
    result["licenses"] = list({lic["id"]: lic for lic in needed if lic}.values())
    changed: list[str] = []
    if apply:
        with config.settings_lock:
            settings = config.load_settings()
            changed = apply_picks(settings, result["agents"])
            if set_fallback and result["fallback_model"]:
                settings["run"]["fallback_model"] = result["fallback_model"]
            config.save_settings(settings)
    return {**result, "applied": changed}


# ─── Modes ───────────────────────────────────────────────────


def current_mode(settings: dict) -> str:
    """privacy, hybrid, cloud, or custom when the crew matches none of them."""
    if settings["run"].get("privacy_mode"):
        return "privacy"
    endpoints = settings.get("endpoints")
    crew = [
        (roles.role_of(name, cfg), providers.is_local(cfg.get("model") or "", endpoints))
        for name, cfg in settings["agents"].items()
        if isinstance(cfg, dict)
    ]
    if crew and not any(local for _, local in crew):
        return "cloud"
    if any(not local for _, local in crew) and all(local == (role not in CLOUD_ROLES) for role, local in crew):
        return "hybrid"
    return "custom"


def set_mode(
    settings: dict,
    mode: str,
    cloud_model: str | None,
    pick_local: Callable[[dict[str, str]], Mapping[str, dict | None]],
) -> dict:
    """Switch the crew to a mode, in place, changing only the agents that must move.

    Agents that must run locally and don't get a local model from
    pick_local(name -> role). Agents that must run in the cloud get
    cloud_model, or keep the cloud model they have.
    """
    if mode not in MODES:
        raise ValueError(f"Mode must be one of {', '.join(MODES)}")
    endpoints = settings.get("endpoints")
    if cloud_model:
        provider = cloud_model.partition(":")[0]
        if providers.provider_info(provider, endpoints) is None:
            raise ValueError(f"Unknown provider '{provider}' in model '{cloud_model}'")
        if providers.is_local(cloud_model, endpoints):
            raise ValueError(f"{cloud_model} runs locally; pick a cloud model")

    agents = {name: cfg for name, cfg in settings["agents"].items() if isinstance(cfg, dict)}
    role = {name: roles.role_of(name, cfg) for name, cfg in agents.items()}
    local = {name: providers.is_local(cfg.get("model") or "", endpoints) for name, cfg in agents.items()}
    cloud = {name: mode == "cloud" or (mode == "hybrid" and role[name] in CLOUD_ROLES) for name in agents}
    if not cloud_model:
        stuck = [name for name in agents if cloud[name] and local[name]]
        if stuck:
            raise ValueError(f"Pick a cloud model for {', '.join(stuck)}")

    changed: dict[str, str] = {}
    warnings: list[str] = []
    to_local = {name: role[name] for name in agents if not cloud[name] and not local[name]}
    picks = pick_local(to_local) if to_local else {}
    for name in to_local:
        pick = picks.get(name)
        if pick:
            agents[name]["model"], agents[name]["num_ctx"] = pick["model"], pick["num_ctx"]
            if not pick.get("installed"):
                warnings.append(f"{name} now uses {pick['model']}, which isn't downloaded yet; download it before a run")
        else:
            agents[name]["model"] = roles.DEFAULT_MODEL
            agents[name].pop("num_ctx", None)
            warnings.append(f"No catalogue model fits this machine for {name}; it uses {roles.DEFAULT_MODEL}")
        changed[name] = agents[name]["model"]
    for name, agent in agents.items():
        if cloud[name] and cloud_model and agent.get("model") != cloud_model:
            agent["model"] = cloud_model
            agent.pop("num_ctx", None)  # num_ctx is for Ollama only
            changed[name] = cloud_model
    settings["run"]["privacy_mode"] = mode == "privacy"

    to_cloud = [name for name in agents if cloud[name]]
    notice = ""
    if to_cloud:
        used = sorted({agents[name]["model"].partition(":")[0] for name in to_cloud})
        notice = (
            f"In {mode.capitalize()} mode, prompts and code for {', '.join(to_cloud)} go to {', '.join(used)}. "
            "Privacy Mode keeps everything on this machine."
        )
        for provider in used:
            info = providers.provider_info(provider, endpoints) or {}
            if info.get("key", True) and not keystore.get_key(provider):
                warnings.append(f"No API key is set for {provider} yet")
    return {"mode": mode, "changed": changed, "warnings": warnings, "notice": notice}


def switch_mode(mode: str, cloud_model: str | None = None) -> dict:
    """Switch the saved crew to a mode, picking local models with Auto-Crew."""
    endpoints = config.load_settings().get("endpoints")
    hw, have = hardware.current(), ollama.installed(endpoints)
    with config.settings_lock:
        settings = config.load_settings()
        result = set_mode(settings, mode, cloud_model, lambda agents: auto_crew(hw, have, agents)["agents"])
        config.save_settings(settings)
    return result
