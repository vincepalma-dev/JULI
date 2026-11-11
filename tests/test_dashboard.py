"""What the dashboard relies on: structured status, run ids on messages, stored
message data, the runs listing, one-origin serving with its own CSP, and `juli serve`."""

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from juli import cli, store
from juli.api.app import create_app
from juli.api.security import API_CSP
from juli.bus import AgentMessage, MessageBus, message_bus

from .conftest import AUTH, TOKEN
from .test_history import start


def test_status_messages_carry_the_status():
    bus = MessageBus()
    seen = []
    bus.subscribe_sync(seen.append)
    bus.set_task_status("paused")
    assert seen[-1].message_type == "status"
    assert seen[-1].data == {"status": "paused"}


def test_messages_carry_their_run_id():
    bus = MessageBus()
    bus.start_run("p1", 7)
    bus.publish(AgentMessage(agent_name="Coder", content="x"))
    assert bus.history[-1].run_id == 7
    assert bus.history[-1].to_dict()["run_id"] == 7


def test_activating_another_project_clears_the_live_view():
    bus = MessageBus()
    bus.start_run("p1", 1)
    bus.publish(AgentMessage(agent_name="Coder", content="x"))
    assert bus.set_active_project("p1") is True
    assert len(bus.history) == 1  # same project: the live view stays
    assert bus.set_active_project("p2") is True
    assert bus.history == [] and bus.active_run_id is None


def test_stored_messages_keep_run_id_and_data():
    store.init_db()
    pid = store.create_project("P")["id"]
    run_id = store.create_run(pid, "task", "full")
    data = {"kind": "command_approval", "command": "pytest -q", "options": ["approve", "deny"]}
    store.save_message(pid, run_id, {"agent_name": "System", "content": "ok?", "message_type": "decision", "data": data})
    store.save_message(pid, run_id, {"agent_name": "Coder", "content": "code"})
    first, second = store.get_project(pid)["messages"]
    assert (first["run_id"], first["data"]) == (run_id, data)
    assert second["data"] is None


def test_runs_listing(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = start(client, pid, "one")
    runs = client.get(f"/api/projects/{pid}/runs", headers=AUTH).json()
    assert [(r["id"], r["prompt"], r["status"]) for r in runs] == [(run_id, "one", "complete")]
    assert "checkpoint" not in runs[0]
    assert client.get("/api/projects/nope/runs", headers=AUTH).status_code == 404


def test_status_route_names_the_active_run(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = start(client, pid, "one")
    body = client.get("/api/status", headers=AUTH).json()
    assert (body["status"], body["project_id"], body["run_id"]) == ("complete", pid, run_id)


def test_ws_greeting_has_structured_status(client):
    message_bus._task_status = "paused"
    with client.websocket_connect("/ws", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_json({"type": "auth", "token": TOKEN})
        hello = ws.receive_json()
    assert hello["message_type"] == "status" and hello["data"] == {"status": "paused"}


# ─── One origin ──────────────────────────────────────────────


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "mascot").mkdir()
    (root / "index.html").write_text("<!doctype html><title>JULI</title>", encoding="utf-8")
    (root / "assets" / "app-1234.js").write_text("console.log(1)", encoding="utf-8")
    (root / "mascot" / "still.png").write_bytes(b"\x89PNG")
    return root


def test_dashboard_is_served_with_its_own_csp(dist):
    with TestClient(create_app(token=TOKEN, static_dir=dist, port=8000)) as c:
        page = c.get("/")
        asset = c.get("/assets/app-1234.js")
        api = c.get("/api/status", headers=AUTH)
        assert page.status_code == 200 and "JULI" in page.text
        assert asset.status_code == 200 and c.get("/mascot/still.png").status_code == 200
        csp = page.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "connect-src 'self' ws://127.0.0.1:8000 ws://localhost:8000" in csp
        assert "unsafe-eval" not in csp
        assert asset.headers["content-security-policy"] == csp
        assert api.headers["content-security-policy"] == API_CSP
        assert c.get("/api/health").headers["content-security-policy"] == API_CSP
        for r in (page, asset, api):
            assert r.headers["x-frame-options"] == "DENY"
            assert r.headers["x-content-type-options"] == "nosniff"
            assert r.headers["referrer-policy"] == "no-referrer"


def test_no_dashboard_without_static_dir(client):
    assert client.get("/").status_code == 404


def test_missing_build_refuses_to_serve(tmp_path):
    with pytest.raises(RuntimeError, match="isn't built"):
        create_app(token=TOKEN, static_dir=tmp_path / "missing")


def test_build_without_assets_refuses_to_serve(dist):
    import shutil

    shutil.rmtree(dist / "assets")
    with pytest.raises(RuntimeError, match=r"isn't built: .*assets missing"):
        create_app(token=TOKEN, static_dir=dist)


class FakeServer:
    """Stands in for uvicorn.Server: 'starts' at once and returns."""

    instances: ClassVar[list] = []

    def __init__(self, config):
        self.config = config
        self.started = False
        self.should_exit = False
        FakeServer.instances.append(self)

    def run(self):
        self.started = True
        import time

        time.sleep(0.3)  # let the opener thread see it


@pytest.fixture
def fake_serve(monkeypatch, dist):
    import uvicorn

    opened = []
    builds = []
    FakeServer.instances = []
    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setattr(cli, "FRONTEND_DIR", dist.parent)
    monkeypatch.setattr(cli, "build_dashboard", lambda: builds.append(1))
    monkeypatch.setattr("webbrowser.open", opened.append)
    return opened, builds


def test_serve_opens_the_dashboard_without_printing_the_token(fake_serve):
    opened, builds = fake_serve
    result = CliRunner().invoke(cli.app, ["serve"])
    assert result.exit_code == 0, result.output
    assert builds == []  # dist/index.html exists
    server = FakeServer.instances[0]
    assert (server.config.host, server.config.port) == ("127.0.0.1", 8000)
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:8000/#token=")
    token = opened[0].split("#token=")[1]
    assert token not in result.output


def test_serve_prints_the_link_only_when_asked(fake_serve):
    opened, _ = fake_serve
    result = CliRunner().invoke(cli.app, ["serve", "--no-browser", "--show-link"])
    assert result.exit_code == 0, result.output
    assert opened == []
    assert "http://127.0.0.1:8000/#token=" in "".join(result.output.split())


def test_serve_builds_when_the_dashboard_is_missing(fake_serve, dist, monkeypatch):
    _, builds = fake_serve
    (dist / "index.html").unlink()

    def build():
        builds.append(1)
        (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")

    monkeypatch.setattr(cli, "build_dashboard", build)
    result = CliRunner().invoke(cli.app, ["serve", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert builds == [1]


def test_serve_explains_a_missing_source_tree(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "FRONTEND_DIR", tmp_path / "no-frontend")  # e.g. a regular, non-editable install
    result = CliRunner().invoke(cli.app, ["serve", "--no-browser"])
    assert result.exit_code == 1
    assert "runs from a clone of its repository" in " ".join(result.output.split())


def test_settings_report_each_agents_effective_role(client):
    agents = client.get("/api/settings", headers=AUTH).json()["agents"]
    assert agents["Coder"]["role"] == "coder"
    assert agents["DevOps"]["role"] == "custom"


def test_providers_mark_custom_endpoints(client):
    from juli import config

    with config.settings_lock:
        settings = config.load_settings()
        settings["endpoints"] = {"lmstudio": {"label": "LM Studio", "base_url": "http://localhost:1234/v1", "key": False}}
        config.save_settings(settings)
    listed = {p["id"]: p for p in client.get("/api/providers", headers=AUTH).json()}
    assert listed["lmstudio"]["custom"] is True and listed["lmstudio"]["local"] is True
    assert listed["lmstudio"]["base_url"] == "http://localhost:1234/v1"
    assert listed["openai"]["custom"] is False


def test_dashboard_answers_head(dist):
    with TestClient(create_app(token=TOKEN, static_dir=dist)) as c:
        r = c.head("/")
        assert r.status_code == 200 and "script-src 'self'" in r.headers["content-security-policy"]


def test_serve_keeps_a_preset_origin_list_and_adds_its_own(fake_serve, monkeypatch):
    import os

    monkeypatch.setenv("JULI_ALLOWED_ORIGINS", "http://example.test:3000")
    assert CliRunner().invoke(cli.app, ["serve", "--no-browser"]).exit_code == 0
    assert os.environ["JULI_ALLOWED_ORIGINS"].split(",") == [
        "http://example.test:3000",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]


def test_serve_on_another_port_allows_that_origin(fake_serve):
    import os

    assert CliRunner().invoke(cli.app, ["serve", "--port", "8040", "--no-browser"]).exit_code == 0
    assert os.environ["JULI_ALLOWED_ORIGINS"].split(",") == ["http://127.0.0.1:8040", "http://localhost:8040"]
