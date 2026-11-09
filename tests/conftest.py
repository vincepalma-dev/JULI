import json
import threading
import types
from pathlib import Path

import httpx
import httpx2
import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from juli import config, keystore, providers
from juli.api.app import create_app
from juli.bus import AgentMessage, message_bus
from juli.local import hardware, ollama
from juli.local.hardware import Readings

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
    for var in [keystore.env_var(p) for p in providers.PROVIDERS] + ["JULI_TOKEN", "JULI_ALLOWED_ORIGINS"]:
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


class FakeNet:
    """Serves recorded responses to the provider SDKs (httpx2) and httpx.

    With no handler set, every request fails as if offline, so no test can
    reach the network. A handler takes the request and returns
    (status, body, headers); a dict or list body is sent as JSON.
    """

    def __init__(self) -> None:
        self.handler = None
        self.requests: list = []

    def transport(self, lib):
        def handle(request):
            self.requests.append(request)
            if self.handler is None:
                raise lib.ConnectError("network disabled in tests", request=request)
            status, body, headers = self.handler(request)
            headers = dict(headers or {})
            if isinstance(body, (dict, list)):
                body = json.dumps(body)
                headers.setdefault("content-type", "application/json")
            if isinstance(body, str):
                body = body.encode()
            return lib.Response(status, headers=headers, content=body)

        return lib.MockTransport(handle)


@pytest.fixture(autouse=True)
def net(monkeypatch):
    fake = FakeNet()
    monkeypatch.setattr(providers, "SDK_HTTP_CLIENT", lambda: httpx2.Client(transport=fake.transport(httpx2)))
    monkeypatch.setattr(providers, "HTTP_TRANSPORT", fake.transport(httpx))
    return fake


@pytest.fixture
def fake_engine(monkeypatch):
    """Stand-in for juli.engine.execute: no model calls, a fixed answer and usage."""
    from juli import engine

    calls = []
    done = threading.Event()

    def execute(run):
        run.bus.publish(
            AgentMessage(
                agent_name="Coder",
                content=f"answer to {run.prompt}",
                model="openai:gpt-6.1-sol",
                tokens_in=10,
                tokens_out=5,
                cost_usd=0.001,
            )
        )
        run.bus.set_task_status("complete")
        calls.append(run)
        done.set()
        return engine.RunResult("complete", 10, 5, 0.001)

    monkeypatch.setattr(engine, "execute", execute)
    return types.SimpleNamespace(calls=calls, done=done)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def serve(routes: dict):
    """A FakeNet handler from {(method, path): (status, body, headers) or callable}."""

    def handler(request):
        route = routes.get((request.method, request.url.path))
        if route is None:
            return 404, {"error": f"no fixture for {request.method} {request.url.path}"}, {}
        return route(request) if callable(route) else route

    return handler


LAPTOP = Readings(
    system="Windows",
    machine="AMD64",
    cpu="11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz",
    cores=4,
    ram_bytes=16_000_000_000,
    disk_free_bytes=40_000_000_000,
    models_dir=r"C:\Users\me\.ollama\models",
    windows_gpus=[("Intel(R) Iris(R) Xe Graphics", None)],
)


@pytest.fixture
def laptop(monkeypatch):
    """A 16 GB CPU-only machine with 40 GB of free disk, instead of the real one."""
    monkeypatch.setattr(hardware, "read", lambda: LAPTOP)
    return hardware.detect(LAPTOP)


@pytest.fixture(autouse=True)
def fresh_pulls(monkeypatch):
    jobs = ollama.PullJobs()
    monkeypatch.setattr(ollama, "PULLS", jobs)
    return jobs
