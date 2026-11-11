import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta

import pytest

from juli import config, data, keystore, mcp, store, workspace
from juli.bus import message_bus

from .conftest import AUTH, TOKEN
from .test_engine import make_settings


def days_ago(n: float) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).isoformat()


@pytest.fixture
def project():
    store.init_db()
    return store.create_project("P")["id"]


def finished_run(project_id: str, ended: str | None) -> int:
    run_id = store.create_run(project_id, "task", "code")
    store.save_message(project_id, run_id, {"agent_name": "Coder", "content": "secret prompt output", "message_type": "agent"})
    store.record_file(run_id, "a.py", None, "x = 1\n")
    with store.connect() as conn:
        conn.execute("UPDATE runs SET ended_at = ?, status = ? WHERE id = ?", (ended, "complete" if ended else "running", run_id))
    return run_id


def run_ids(project_id: str) -> list[int]:
    return [r["id"] for r in store.get_runs(project_id)]


# ─── Retention ───────────────────────────────────────────────


def test_old_runs_go_with_their_messages_and_files(project):
    old, recent, unfinished = finished_run(project, days_ago(40)), finished_run(project, days_ago(5)), finished_run(project, None)
    with store.connect() as conn:  # a message from before runs existed
        conn.execute(
            "INSERT INTO messages (project_id, agent_name, content, timestamp, message_type) VALUES (?, 'X', 'old', ?, 'agent')",
            (project, days_ago(50)),
        )

    assert data.apply_retention({"data": {"retention_days": 30}}) == 1
    assert run_ids(project) == [recent, unfinished]  # a run that hasn't ended is never pruned
    assert store.run_messages(old) == [] and store.run_files(old) == []
    assert [m["content"] for m in store.get_project(project)["messages"]] == ["secret prompt output", "secret prompt output"]


def test_no_retention_period_keeps_everything(project):
    finished_run(project, days_ago(4000))
    assert data.apply_retention({"data": {"retention_days": None}}) == 0
    assert data.apply_retention(make_settings()) == 0
    assert len(run_ids(project)) == 1


def test_saving_a_retention_period_applies_it_at_once(client, project):
    finished_run(project, days_ago(100))
    finished_run(project, days_ago(10))
    assert client.get("/api/settings", headers=AUTH).json()["data"] == {"retention_days": None}

    r = client.put("/api/settings/data", json={"retention_days": 90}, headers=AUTH)
    assert r.json() == {"status": "saved", "data": {"retention_days": 90}, "deleted_runs": 1}
    assert client.get("/api/settings", headers=AUTH).json()["data"] == {"retention_days": 90}
    assert client.put("/api/settings/data", json={}, headers=AUTH).json()["data"] == {"retention_days": None}


@pytest.mark.parametrize("body", [{"retention_days": 0}, {"retention_days": 3651}, {"retention_days": "a month"}, {"days": 30}])
def test_retention_settings_are_validated(client, body):
    assert client.put("/api/settings/data", json=body, headers=AUTH).status_code == 422


def test_retention_runs_at_startup(project):
    finished_run(project, days_ago(400))
    settings = config.load_settings()
    settings["data"] = {"retention_days": 365}
    config.save_settings(settings)
    from fastapi.testclient import TestClient

    from juli.api.app import create_app

    with TestClient(create_app(token=TOKEN)):
        pass
    assert run_ids(project) == []


def test_retention_runs_after_each_task(client, fake_engine):
    settings = make_settings()
    settings["data"] = {"retention_days": 30}
    config.save_settings(settings)
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    old = finished_run(pid, days_ago(31))
    r = client.post("/api/task", json={"prompt": "go", "project_id": pid, "mode": "code"}, headers=AUTH)
    assert r.status_code == 202
    fake_engine.done.wait(5)
    from .test_engine import wait_for

    wait_for(lambda: old not in run_ids(pid))
    assert run_ids(pid) == [r.json()["run_id"]]


# ─── Delete all ──────────────────────────────────────────────


def test_delete_all_removes_everything_juli_stores(client, project, memory_keyring):
    finished_run(project, days_ago(1))
    store.save_benchmark("ollama:x", 10.0, None, "hw")
    base = workspace.ensure(project)
    (base / "app.py").write_text("print(1)\n", encoding="utf-8")
    locked = base / "locked.txt"
    locked.write_text("read-only, like git's objects\n", encoding="utf-8")
    os.chmod(locked, stat.S_IREAD)

    settings = config.load_settings()
    settings["endpoints"] = {"lmstudio": {"label": "LM Studio", "base_url": "http://127.0.0.1:1234/v1"}}
    settings["mcp_servers"] = {"gh": {"transport": "stdio", "command": ["x"]}}
    settings["run"]["token_cap"] = 5000
    config.save_settings(settings)
    for name in ("openai", "lmstudio", mcp.token_key("gh")):
        keystore.set_key(name, f"secret-{name}")

    r = client.post("/api/data/delete-all", json={"confirm": "delete all data"}, headers=AUTH)
    assert r.json() == {"status": "deleted", "problems": []}

    assert store.get_projects() == [] and store.get_benchmarks("hw") == {}
    assert not (config.data_dir() / "workspace").exists()
    assert memory_keyring.store == {}
    assert config.load_settings() == config.default_settings()
    assert b"secret prompt output" not in config.db_path().read_bytes()  # not left in free pages


def test_delete_all_needs_the_phrase(client, project):
    for body in ({}, {"confirm": "yes"}, {"confirm": "DELETE ALL DATA"}):
        assert client.post("/api/data/delete-all", json=body, headers=AUTH).status_code == 422
    assert len(store.get_projects()) == 1


def test_delete_all_waits_for_a_running_task(client, project):
    message_bus._task_status = "running"
    try:
        r = client.post("/api/data/delete-all", json={"confirm": "delete all data"}, headers=AUTH)
    finally:
        message_bus._task_status = "idle"
    assert r.status_code == 409 and r.json()["detail"] == "A task is running. Stop it first."
    assert len(store.get_projects()) == 1


def test_delete_all_clears_the_live_view(client, project):
    message_bus.active_project_id, message_bus.active_run_id = project, 3
    client.post("/api/data/delete-all", json={"confirm": "delete all data"}, headers=AUTH)
    assert (message_bus.active_project_id, message_bus.active_run_id, message_bus.history) == (None, None, [])


def test_delete_all_says_what_it_couldnt_do(client, project, monkeypatch):
    def unavailable(name):
        raise keystore.KeystoreUnavailable("no keychain")

    def busy(path):
        raise PermissionError(13, "in use")

    workspace.ensure(project)
    monkeypatch.setattr(keystore, "delete_key", unavailable)
    monkeypatch.setattr(data, "_remove_tree", busy)
    r = client.post("/api/data/delete-all", json={"confirm": "delete all data"}, headers=AUTH).json()
    assert r["status"] == "partly deleted"
    assert r["problems"] == [
        "Some workspace files couldn't be deleted (in use). Close the terminal and try again.",
        "The system keychain isn't available, so no keys were removed from it.",
    ]
    assert store.get_projects() == []  # the rest still went


def test_a_database_failure_in_delete_all_still_does_the_rest(client, project, memory_keyring, monkeypatch):
    def locked():
        raise sqlite3.OperationalError("database is locked")

    keystore.set_key("openai", "secret-openai")
    workspace.ensure(project)
    monkeypatch.setattr(store, "delete_all", locked)
    r = client.post("/api/data/delete-all", json={"confirm": "delete all data"}, headers=AUTH).json()
    assert r == {
        "status": "partly deleted",
        "problems": ["The projects and run history couldn't be deleted (database is locked). Close other JULI windows and try again."],
    }
    assert not (config.data_dir() / "workspace").exists() and memory_keyring.store == {}


def test_retention_failures_never_stop_a_run_or_startup(project, monkeypatch, caplog):
    def locked(before):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "prune_runs", locked)
    assert data.apply_retention({"data": {"retention_days": 30}}) == 0
    assert "Couldn't delete old runs" in caplog.text

    def broken(settings=None):
        raise ValueError("retention_days isn't a number")

    monkeypatch.setattr(data, "apply_retention", broken)
    from fastapi.testclient import TestClient

    from juli.api.app import create_app

    with TestClient(create_app(token=TOKEN)) as c:
        assert c.get("/api/health").status_code == 200
    assert "Applying the retention period failed" in caplog.text


def test_delete_all_is_rate_limited(client):
    codes = [client.post("/api/data/delete-all", json={"confirm": "delete all data"}, headers=AUTH).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
