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

from juli import keystore

log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent

# Where settings.json lived before it moved into the data directory.
LEGACY_SETTINGS_FILE = ROOT_DIR / "settings.json"

DEFAULT_PROVIDERS = ["openai", "anthropic", "google"]
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
    # The prompts still live with the AutoGen agents until the Phase 3 engine.
    from agents.agents import AGENT_COLORS, SYSTEM_PROMPTS

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
        "providers": list(DEFAULT_PROVIDERS),
        "available_models": list(DEFAULT_MODELS),
    }


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
    data.setdefault("available_models", list(DEFAULT_MODELS))
    return data


def save_settings(settings: dict) -> None:
    clean = {k: v for k, v in settings.items() if k != "api_keys"}
    _write_json_atomic(settings_path(), clean)


def migrate_legacy_settings() -> None:
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
            "OS keychain unavailable: API keys in %s were not migrated. "
            "Move them to a .env file (see .env.example).",
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
