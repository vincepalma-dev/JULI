import time

from juli import store
from juli.bus import message_bus

from .conftest import AUTH


def wait_idle(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runs_done = all(r["ended_at"] for p in store.get_projects() for r in store.get_runs(p["id"]))
        if message_bus.task_status != "running" and runs_done:
            return
        time.sleep(0.02)
    raise AssertionError("task did not finish")


def start(client, project_id, prompt):
    r = client.post("/api/task", json={"prompt": prompt, "project_id": project_id}, headers=AUTH)
    assert r.status_code == 202, r.text
    wait_idle()
    return r.json()["run_id"]


def test_history_survives_a_second_task(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    first = start(client, pid, "one")
    second = start(client, pid, "two")

    assert first != second
    runs = store.get_runs(pid)
    assert [r["prompt"] for r in runs] == ["one", "two"]
    assert all(r["status"] == "complete" for r in runs)

    contents = [m["content"] for m in client.get(f"/api/projects/{pid}", headers=AUTH).json()["messages"]]
    assert contents == ["answer to one", "answer to two"]
    # The live view shows only the latest run.
    live = [m["content"] for m in client.get("/api/messages", headers=AUTH).json()]
    assert live == ["answer to two", "Task status: complete"]


def test_second_task_while_running_is_409(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    assert message_bus.try_begin_task("busy")
    r = client.post("/api/task", json={"prompt": "x", "project_id": pid}, headers=AUTH)
    assert r.status_code == 409


def test_delete_project_cascades(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    start(client, pid, "one")
    assert client.delete(f"/api/projects/{pid}", headers=AUTH).status_code == 204
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_old_database_gains_run_columns(tmp_path):
    import sqlite3

    from juli import config

    db = config.db_path()
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
                               updated_at TEXT NOT NULL);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
            agent_name TEXT NOT NULL, content TEXT NOT NULL, timestamp TEXT NOT NULL,
            message_type TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE);
        INSERT INTO projects VALUES ('p1', 'Old', '2025-01-01', '2025-01-01');
        INSERT INTO messages (project_id, agent_name, content, timestamp, message_type)
            VALUES ('p1', 'Coder', 'kept', '2025-01-01', 'agent');
    """)
    conn.close()

    store.init_db()

    assert store.get_project("p1")["messages"][0]["content"] == "kept"
    run_id = store.create_run("p1", "new", "full")
    store.save_message("p1", run_id, {"agent_name": "Coder", "content": "new"})
    assert len(store.get_project("p1")["messages"]) == 2


def test_deleting_the_active_project_stops_routing_messages_to_it(client):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    client.put(f"/api/projects/{pid}/activate", headers=AUTH)
    assert client.delete(f"/api/projects/{pid}", headers=AUTH).status_code == 204
    assert message_bus.active_project_id is None
