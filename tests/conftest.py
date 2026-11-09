import sys
import threading
import types

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from juli import config, keystore
from juli.api.app import create_app
from juli.bus import message_bus

TOKEN = "test-token-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError("not found")
        del self.store[(service, username)]


@pytest.fixture
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch, memory_keyring):
    """Every test gets its own data dir, keychain, env and an idle bus."""
    monkeypatch.setenv("JULI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "LEGACY_SETTINGS_FILE", tmp_path / "legacy-settings.json")
    monkeypatch.setattr(keystore, "ENV_FILE", tmp_path / ".env")
    keystore._dotenv.cache_clear()
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "JULI_TOKEN", "JULI_ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    message_bus._task_status = "idle"
    message_bus.active_project_id = None
    message_bus.active_run_id = None
    message_bus.clear_history()
    yield
    keystore._dotenv.cache_clear()


@pytest.fixture
def client():
    with TestClient(create_app(token=TOKEN)) as c:
        yield c


@pytest.fixture
def fake_engine(monkeypatch):
    """Stand-in for agents.orchestrator, so tests never need pyautogen."""
    calls = []
    done = threading.Event()

    def run_task(prompt, **kwargs):
        from juli.bus import AgentMessage

        message_bus.publish(AgentMessage(agent_name="Coder", content=f"answer to {prompt}"))
        message_bus.set_task_status("complete")
        calls.append(prompt)
        done.set()

    module = types.ModuleType("agents.orchestrator")
    module.run_task = run_task  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents.orchestrator", module)
    return types.SimpleNamespace(calls=calls, done=done)
