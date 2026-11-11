"""
Paths and settings.

settings.json lives in the data directory and never holds secrets: API keys
are kept by juli.keystore. Writes are atomic (temp file, then os.replace).
"""

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from juli import keystore, roles

log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent

# Where settings.json lived before it moved into the data directory.
LEGACY_SETTINGS_FILE = ROOT_DIR / "settings.json"

DEFAULT_PROVIDERS = ["openai", "anthropic", "google"]

# Optional run limits and switches. Empty (None) means no limit.
DEFAULT_RUN: dict[str, Any] = {
    "budget_usd": None,
    "token_cap": None,
    "privacy_mode": False,
    "auto_fallback": False,
    "fallback_model": None,
    "discussion_rounds": 0,  # crew discussion of the plan; 0 is off
    "allowances": {},
}

# The Docker sandbox for agent commands. Off by default: every command then
# asks first. The image must already hold the tools the commands use
# (pytest, npm...), since the container has no network.
DEFAULT_SANDBOX = {
    "enabled": False,
    "image": "python:3.12-slim",
    "timeout": 120,  # seconds per command, in or out of the sandbox
}

# Model keys saved before provider:model refs, mapped to the verified presets.
LEGACY_MODEL_REFS = {
    "gpt4": "openai:gpt-6.1-sol",
    "claude": "anthropic:claude-opus-5-5",
    "gemini": "google:gemini-4-argon",
    "gemini_flash": "google:gemini-3.8-flash",
}

# Serialises read-modify-write cycles on settings.json across request threads.
settings_lock = threading.Lock()


def data_dir() -> Path:
    """The data directory: $JULI_DATA_DIR, or ./data next to the code."""
    path = Path(os.environ.get("JULI_DATA_DIR") or ROOT_DIR / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return data_dir() / "settings.json"


def db_path() -> Path:
    return data_dir() / "projects.db"


def default_settings() -> dict:
    return {
        "agents": {
            name: {
                "role": roles.DEFAULT_ROLES[name],
                "model": roles.DEFAULT_AGENT_MODEL_MAP[name],
                "prompt": prompt,
                "color": roles.AGENT_COLORS.get(name, "#6b7280"),
                "icon": roles.DEFAULT_AGENT_ICONS.get(name, "system"),
                "job_title": f"{name} Specialist",
            }
            for name, prompt in roles.SYSTEM_PROMPTS.items()
        },
        "providers": list(DEFAULT_PROVIDERS),
        "available_models": [],
        "run": {**DEFAULT_RUN, "allowances": {}},
        "sandbox": dict(DEFAULT_SANDBOX),
    }


def upgrade_models(data: dict) -> bool:
    """Replace legacy model keys with provider:model refs, in place.

    Only the model fields change; every other user edit is kept. True if
    anything changed.
    """
    changed = False
    for agent in (data.get("agents") or {}).values():
        if isinstance(agent, dict) and agent.get("model") in LEGACY_MODEL_REFS:
            agent["model"] = LEGACY_MODEL_REFS[agent["model"]]
            changed = True
    models = data.get("available_models") or []
    if any(m in LEGACY_MODEL_REFS for m in models):
        upgraded = [LEGACY_MODEL_REFS.get(m, m) for m in models]
        data["available_models"] = list(dict.fromkeys(upgraded))
        changed = True
    return changed


def _read_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_settings() -> dict:
    """Settings from data/settings.json, or the defaults."""
    data = _read_json(settings_path())
    if data is None:
        return default_settings()
    data.pop("api_keys", None)  # never hand legacy secrets onwards
    data.setdefault("agents", {})
    data.setdefault("providers", list(DEFAULT_PROVIDERS))
    data.setdefault("available_models", [])
    data["run"] = {**DEFAULT_RUN, "allowances": {}, **(data.get("run") or {})}
    data["sandbox"] = {**DEFAULT_SANDBOX, **(data.get("sandbox") or {})}
    upgrade_models(data)
    return data


def save_settings(settings: dict) -> None:
    clean = {k: v for k, v in settings.items() if k != "api_keys"}
    _write_json_atomic(settings_path(), clean)


def migrate_legacy_settings() -> None:
    """Startup migrations: keys into the keychain, legacy model keys to refs."""
    _migrate_keys()
    with settings_lock:
        data = _read_json(settings_path())
        if data is not None and upgrade_models(data):
            save_settings(data)
            log.info("Updated saved agent models to provider:model refs.")


def _migrate_keys() -> None:
    """
    Move API keys out of settings.json and into the OS keychain.

    Reads data/settings.json, or the legacy ./settings.json when the new file
    doesn't exist yet. Non-empty keys go to the keychain; only then are they
    blanked in the file they came from. If the keychain is unavailable, the
    keys are left where they are and a warning is logged.
    """
    new_path = settings_path()
    from_legacy = not new_path.exists()
    source = LEGACY_SETTINGS_FILE if from_legacy else new_path
    data = _read_json(source)
    if data is None:
        return

    keys = data.get("api_keys") or {}
    stored_all = True
    for provider, key in keys.items():
        if key:
            try:
                keystore.set_key(provider, str(key))
            except keystore.KeystoreUnavailable:
                stored_all = False
    if not stored_all:
        log.warning(
            "OS keychain unavailable: API keys in %s were not migrated. Move them to a .env file (see .env.example).",
            source,
        )
        return

    with settings_lock:
        if from_legacy or "api_keys" in data:
            migrated = {k: v for k, v in data.items() if k != "api_keys"}
            providers = list(migrated.get("providers") or [])
            providers += [p for p in keys if p not in providers]
            migrated["providers"] = providers or list(DEFAULT_PROVIDERS)
            save_settings(migrated)

        if from_legacy and any(keys.values()):
            data["api_keys"] = {provider: "" for provider in keys}
            _write_json_atomic(LEGACY_SETTINGS_FILE, data)
            log.info("Moved API keys from %s into the OS keychain.", source)
