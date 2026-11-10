import json

import pytest
from typer.testing import CliRunner

from juli import cli, config, engine, providers, store, workspace
from juli.bus import MessageBus, message_bus

from .conftest import AUTH, docker_up
from .test_engine import (
    APPROVED,
    Models,
    make_run,
    make_settings,
    of_type,
    run_in_thread,
    wait_for,
)

SANDBOX = {"enabled": True, "image": "python:3.12-slim", "timeout": 30}


@pytest.fixture
def models(monkeypatch):
    fake = Models({"ollama:review": APPROVED})
    monkeypatch.setattr(providers, "stream", fake)
    return fake


@pytest.fixture
def bus():
    bus = MessageBus()
    bus.events = []
    bus.subscribe_sync(bus.events.append)
    return bus


@pytest.fixture
def project():
    store.init_db()
    return store.create_project("P")["id"]


def start_task(client, settings=None, **body):
    config.save_settings(settings or make_settings())
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    r = client.post("/api/task", json={"prompt": "Build a todo app", "project_id": pid, "mode": "code", **body}, headers=AUTH)
    assert r.status_code == 202, r.text
    return pid, r.json()["run_id"]


def ended(run_id):
    wait_for(lambda: store.get_run(run_id)["ended_at"])
    return store.get_run(run_id)


# ─── Saving ──────────────────────────────────────────────────


def test_a_checkpoint_follows_every_step(models, bus, project):
    run = make_run(bus, "code", approve_plan=True)
    run_id = engine.begin(project, run)
    saved = []
    save = run.on_checkpoint
    run.on_checkpoint = lambda state, status: (saved.append(([s["kind"] for s in state["steps"]], status)), save(state, status))

    thread, _ = run_in_thread(run)
    wait_for(lambda: store.get_run(run_id)["status"] == "paused")
    state = json.loads(store.get_checkpoint(run_id))
    assert state["prompt"] == "Build a todo app" and state["options"]["approve_plan"] is True
    assert [a["name"] for a in state["crew"]][:3] == ["Planner", "Coder", "Reviewer"]
    engine.decide("approve")
    thread.join(5)

    assert saved == [
        (["turn"], "running"),
        (["turn"], "paused"),
        (["turn", "decision"], "running"),
        (["turn", "decision", "turn"], "running"),
        (["turn", "decision", "turn", "turn"], "running"),
    ]
    assert json.loads(store.get_checkpoint(run_id))["usage"]["tokens_in"] == 300


def test_store_keeps_a_checkpoint_only_while_the_run_can_resume(project):
    done, failed, stopped = (store.create_run(project, p, "code") for p in ("a", "b", "c"))
    for run_id in (done, failed, stopped):
        store.save_checkpoint(run_id, "{}", "running")
    store.finish_run(done, "complete")
    store.finish_run(failed, "error")
    store.finish_run(stopped, "stopped")
    assert store.get_checkpoint(done) is None and store.get_checkpoint(stopped) is None
    assert store.get_checkpoint(failed) == "{}"
    assert [r["id"] for r in store.resumable_runs(project)] == [failed]
    assert "checkpoint" not in store.get_runs(project)[0] and "checkpoint" not in store.get_run(failed)


# ─── Resuming ────────────────────────────────────────────────


def test_an_errored_run_resumes_without_repeating_finished_turns(client, models):
    models.replies["ollama:review"] = [RuntimeError("Ollama went away"), APPROVED]
    pid, run_id = start_task(client)
    assert ended(run_id)["status"] == "error"
    assert models.refs == ["ollama:plan", "ollama:code", "ollama:review"]  # the review failed
    assert [r["id"] for r in client.get("/api/runs/resumable", headers=AUTH).json()] == [run_id]

    r = client.post(f"/api/runs/{run_id}/resume", headers=AUTH)
    assert r.status_code == 202 and r.json() == {"status": "resumed", "run_id": run_id}
    row = ended(run_id)
    assert row["status"] == "complete" and row["tokens_in"] == 300  # earlier usage carried over
    assert models.refs[3:] == ["ollama:review"]  # only the unfinished turn ran again
    assert "output of ollama:code" in models.calls[3][1][1]["content"]
    assert store.get_checkpoint(run_id) is None
    assert client.get("/api/runs/resumable", headers=AUTH).json() == []
    contents = [m["content"] for m in store.get_project(pid)["messages"]]
    assert "Resuming from the checkpoint: 2 step(s) already done." in contents
    # Replayed turns aren't stored twice.
    assert [m["agent_name"] for m in store.run_messages(run_id) if m["message_type"] == "agent"] == ["Planner", "Coder", "Reviewer"]


def test_a_paused_run_resumes_at_its_decision_after_a_restart(client, models):
    _, run_id = start_task(client, approve_plan=True)
    wait_for(lambda: store.get_run(run_id)["status"] == "paused")
    left_behind = store.get_checkpoint(run_id)

    # Simulate a restart: the in-memory run is gone, its paused checkpoint stays.
    client.post("/api/task/stop", headers=AUTH)
    ended(run_id)
    store.save_checkpoint(run_id, left_behind, "paused")

    assert client.post(f"/api/runs/{run_id}/resume", headers=AUTH).status_code == 202
    wait_for(lambda: message_bus.task_status == "paused")
    assert client.post("/api/task/decision", json={"action": "approve"}, headers=AUTH).status_code == 200
    assert ended(run_id)["status"] == "complete"
    assert models.refs == ["ollama:plan", "ollama:code", "ollama:review"]  # the planner ran once


def test_replayed_commands_do_not_run_again(client, models, procs):
    procs.handler = docker_up()
    models.replies["ollama:code"] = "```python path=app.py\nprint(1)\n```\n```bash run\npytest -q\n```"
    models.replies["ollama:review"] = [RuntimeError("boom"), APPROVED]
    settings = make_settings()
    settings["sandbox"] = SANDBOX
    pid, run_id = start_task(client, settings)
    assert ended(run_id)["status"] == "error"
    runs_before = [a for a in procs.argvs() if a[:2] == ["docker", "run"]]
    assert len(runs_before) == 1

    client.post(f"/api/runs/{run_id}/resume", headers=AUTH)
    assert ended(run_id)["status"] == "complete"
    assert len([a for a in procs.argvs() if a[:2] == ["docker", "run"]]) == 1
    assert (workspace.root(pid) / "app.py").exists()


def test_a_checkpoint_that_does_not_match_continues_live(models, bus):
    settings = make_settings()
    run = make_run(bus, "code", settings)
    state = {**run.checkpoint(), "steps": [{"kind": "turn", "agent": "Somebody", "model": "x", "text": "?"}]}
    resumed = engine.Run.from_checkpoint(state, settings=settings, bus=bus)
    assert resumed.execute().status == "complete"
    assert models.refs == ["ollama:plan", "ollama:code", "ollama:review"]
    assert any("doesn't match" in m.content for m in of_type(bus, "warning"))


def test_a_resumed_run_keeps_its_crew_but_obeys_todays_privacy_mode(models, bus):
    settings = make_settings({"Coder": {"role": "coder", "model": "openai:gpt-6.1-sol"}})
    state = make_run(bus, "code", settings).checkpoint()
    resumed = engine.Run.from_checkpoint(state, settings=make_settings(privacy_mode=True), bus=bus)
    assert [a.model for a in resumed.agents] == ["openai:gpt-6.1-sol"]
    assert resumed.execute().status == "error" and models.calls == []
    assert any("Privacy Mode is on" in m.content for m in of_type(bus, "error"))


def test_resume_route_errors(client):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    assert client.post("/api/runs/999/resume", headers=AUTH).status_code == 404
    done = store.create_run(pid, "p", "code")
    store.finish_run(done, "complete")
    assert client.post(f"/api/runs/{done}/resume", headers=AUTH).status_code == 409
    odd = store.create_run(pid, "p", "code")
    store.save_checkpoint(odd, json.dumps({"version": 99}), "running")
    r = client.post(f"/api/runs/{odd}/resume", headers=AUTH)
    assert r.status_code == 409 and "another version" in r.json()["detail"]
    assert client.post(f"/api/runs/{odd}/resume", json={"extra": 1}, headers=AUTH).status_code == 422


def test_resumable_route_hides_the_active_run(client, project):
    run_id = store.create_run(project, "p", "code")
    store.save_checkpoint(run_id, "{}", "running")
    assert [r["id"] for r in client.get("/api/runs/resumable", headers=AUTH).json()] == [run_id]
    message_bus.try_begin_task("p", project)
    message_bus.start_run(project, run_id)
    assert client.get("/api/runs/resumable", headers=AUTH).json() == []


def test_cli_lists_and_resumes_runs(models):
    config.save_settings(make_settings())
    models.replies["ollama:review"] = [RuntimeError("Ollama went away"), APPROVED]
    out = str(config.data_dir() / "out")
    first = CliRunner().invoke(cli.app, ["run", "Build it", "--code", "-o", out])
    assert first.exit_code == 1 and "juli resume" in " ".join(first.output.split())

    listing = CliRunner().invoke(cli.app, ["resume", "--list"])
    assert "error" in listing.output and "Build it" in listing.output
    result = CliRunner().invoke(cli.app, ["resume", "-o", out])
    text = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "Resuming run" in text and "Run complete" in text
    assert models.refs.count("ollama:plan") == 1
    assert CliRunner().invoke(cli.app, ["resume"]).exit_code == 1  # nothing left to resume
