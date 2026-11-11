import threading
import time

import pytest

from juli import config, engine, providers, store
from juli.bus import MessageBus
from juli.providers import KeyProblem, ProviderError, Usage

from .conftest import AUTH

APPROVED = "Looks good.\nVERDICT: APPROVED"
CHANGES = "Fix the bug.\nVERDICT: CHANGES REQUESTED"


class Models:
    """Fake providers.stream. Each agent uses its own model ref; replies are
    scripted per ref (a string, or a list used in turn)."""

    def __init__(self, replies=None, usage=(100, 50)):
        self.replies = dict(replies or {})
        self.usage = usage
        self.calls: list[tuple[str, list, dict]] = []
        self.on_chunk = None

    def __call__(self, ref, messages, **kwargs):
        self.calls.append((ref, messages, kwargs))
        reply = self.replies.get(ref, f"output of {ref}")
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if isinstance(reply, Exception):
            raise reply
        for word in reply.split(" "):
            if self.on_chunk:
                self.on_chunk()
            yield word + " "
        tokens_in, tokens_out = self.usage
        yield Usage(tokens_in, tokens_out, providers.cost(ref, tokens_in, tokens_out))

    @property
    def refs(self):
        return [ref for ref, _, _ in self.calls]


CREW = {
    "Planner": {"role": "planner", "model": "ollama:plan", "prompt": "Plan it."},
    "Coder": {"role": "coder", "model": "ollama:code", "prompt": "Code it.", "max_tokens": 4000},
    "Reviewer": {"role": "reviewer", "model": "ollama:review", "prompt": "Review it."},
    "DevOps": {"model": "ollama:devops", "prompt": "Ship it."},
    "Tester": {"role": "tester", "model": "ollama:test", "prompt": "Test it."},
    "Docs": {"role": "docs", "model": "ollama:docs", "prompt": "Document it."},
}


def make_settings(agents=None, **run):
    return {"agents": agents or {k: dict(v) for k, v in CREW.items()}, "run": {**config.DEFAULT_RUN, "allowances": {}, **run}}


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


def make_run(bus, mode="full", settings=None, **kwargs):
    settings = settings or make_settings()
    return engine.Run("Build a todo app", mode, engine.build_crew(settings), settings=settings, bus=bus, **kwargs)


def of_type(bus, kind):
    return [m for m in bus.events if m.message_type == kind]


def run_in_thread(run):
    results = []
    thread = threading.Thread(target=lambda: results.append(engine.execute(run)), daemon=True)
    thread.start()
    return thread, results


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met")


# ─── Pipeline ────────────────────────────────────────────────


def test_full_pipeline_runs_every_step_in_order(models, bus):
    models.replies["ollama:review"] = [CHANGES, APPROVED]
    result = make_run(bus).execute()

    assert result.status == "complete"
    assert models.refs == [
        "ollama:plan",
        "ollama:code",
        "ollama:review",
        "ollama:code",
        "ollama:review",
        "ollama:devops",
        "ollama:test",
        "ollama:docs",
    ]
    second_code_brief = models.calls[3][1][1]["content"]
    assert "Fix the bug." in second_code_brief and "output of ollama:code" in second_code_brief
    assert "output of ollama:plan" in models.calls[1][1][1]["content"]


def test_each_turn_streams_chunks_then_one_agent_message(models, bus):
    make_run(bus, mode="plan").execute()
    agent_msgs = of_type(bus, "agent")
    assert [m.agent_name for m in agent_msgs] == ["Planner", "Docs"]
    assert agent_msgs[0].content.strip() == "output of ollama:plan"
    assert (agent_msgs[0].tokens_in, agent_msgs[0].tokens_out, agent_msgs[0].cost_usd) == (100, 50, 0.0)
    assert "".join(m.content for m in of_type(bus, "chunk") if m.agent_name == "Planner") == agent_msgs[0].content


def test_review_loop_stops_at_max_cycles(models, bus):
    models.replies["ollama:review"] = CHANGES
    result = make_run(bus, mode="code", max_cycles=2).execute()
    assert result.status == "complete"
    assert models.refs.count("ollama:code") == 2
    assert any("No approval after 2" in m.content for m in of_type(bus, "warning"))


@pytest.mark.parametrize(
    "mode, refs",
    [
        ("plan", ["ollama:plan", "ollama:docs"]),
        ("code", ["ollama:plan", "ollama:code", "ollama:review"]),
    ],
)
def test_modes_select_steps(models, bus, mode, refs):
    assert make_run(bus, mode=mode).execute().status == "complete"
    assert models.refs == refs


def test_review_mode_reviews_the_given_artifacts(models, bus):
    result = make_run(bus, mode="review", review_source="### Coder\n\ndef add(a, b): return a - b").execute()
    assert result.status == "complete"
    assert models.refs == ["ollama:review"]
    assert "return a - b" in models.calls[0][1][1]["content"]


def test_review_mode_without_anything_to_review_is_an_error(models, bus):
    assert make_run(bus, mode="review").execute().status == "error"
    assert "Nothing to review" in of_type(bus, "error")[0].content
    assert models.calls == []


def test_settings_prompts_models_and_limits_reach_the_calls(models, bus):
    make_run(bus, mode="code").execute()
    ref, messages, kwargs = models.calls[1]
    assert ref == "ollama:code"
    assert messages[0]["content"].startswith("Code it.")
    assert "path=" in messages[0]["content"]  # coder protocol appended
    assert kwargs["max_tokens"] == 4000
    assert models.calls[0][2]["max_tokens"] is None
    assert "VERDICT: APPROVED" in models.calls[2][1][0]["content"]  # reviewer protocol


def test_each_agent_gets_its_configured_model():
    settings = config.default_settings()
    settings["agents"]["DocsDiagram"]["model"] = "google:gemini-3.8-flash"
    crew = {a.name: a for a in engine.build_crew(settings)}
    assert crew["DocsDiagram"].model == "google:gemini-3.8-flash"
    assert crew["Coder"].model == "ollama:qwen3:8b"
    assert crew["DocsDiagram"].role == "docs"
    assert crew["DevOps"].role == "custom"
    steps = engine.cast(list(crew.values()), "full", no_devops=True)
    assert [a.name for a in steps["custom"]] == []


def test_extra_agent_with_a_taken_role_runs_as_custom():
    crew = engine.build_crew(make_settings({**CREW, "Coder2": {"role": "coder", "model": "ollama:c2"}}))
    steps = engine.cast(crew, "full")
    assert [a.name for a in steps["coder"]] == ["Coder"]
    assert [a.name for a in steps["custom"]] == ["DevOps", "Coder2"]


def test_missing_coder_is_an_error(models, bus):
    agents = {k: v for k, v in CREW.items() if k != "Coder"}
    assert make_run(bus, settings=make_settings(agents)).execute().status == "error"


# ─── Limits ──────────────────────────────────────────────────


def test_token_cap_stops_mid_stream_and_keeps_partial_output(models, bus):
    models.replies["ollama:plan"] = " ".join(["word"] * 400)
    result = make_run(bus, settings=make_settings(token_cap=150)).execute()

    assert result.status == "stopped"
    (limit,) = of_type(bus, "limit_reached")
    assert limit.data == {"cap": "token_cap", "limit": 150}
    partial = of_type(bus, "agent")[0].content
    assert 0 < len(partial) < len(models.replies["ollama:plan"])
    assert models.refs == ["ollama:plan"]
    assert result.tokens_in + result.tokens_out > 0


def test_budget_cap_stops_before_the_call_that_would_exceed_it(models, bus):
    agents = {k: {**v, "model": "openai:gpt-6.1-sol"} for k, v in CREW.items()}
    models.usage = (1_000_000, 0)  # $2.00 per call
    result = make_run(bus, settings=make_settings(agents, budget_usd=1.5)).execute()

    assert result.status == "stopped"
    assert models.refs == ["openai:gpt-6.1-sol"]  # the second call would exceed $1.50
    assert result.cost_usd == pytest.approx(2.0)
    assert of_type(bus, "limit_reached")[0].data["cap"] == "budget"


def test_budget_counts_local_models_as_free(models, bus):
    assert make_run(bus, settings=make_settings(budget_usd=0.01)).execute().status == "complete"


def test_no_limits_by_default(models, bus):
    models.usage = (10_000_000, 10_000_000)
    assert make_run(bus).execute().status == "complete"
    assert of_type(bus, "limit_reached") == []


# ─── Stop, pauses, privacy ───────────────────────────────────


def test_stop_between_chunks_keeps_partial_output(models, bus):
    run = make_run(bus)
    models.replies["ollama:plan"] = "a b c d e f"
    models.on_chunk = lambda: run.stop() if len(of_type(bus, "chunk")) >= 2 else None
    result = run.execute()
    assert result.status == "stopped"
    # Stop lands while the third chunk is produced: it's kept, nothing after it.
    assert of_type(bus, "agent")[0].content.strip() == "a b c"
    assert models.refs == ["ollama:plan"]


def test_module_stop_reaches_the_active_run(models, bus):
    models.on_chunk = lambda: time.sleep(0.05)
    models.replies["ollama:plan"] = " ".join(["slow"] * 200)
    run = make_run(bus)
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "chunk"))
    assert engine.stop() is True
    thread.join(5)
    assert results[0].status == "stopped"
    assert bus.task_status == "stopped"
    assert engine.stop() is False


def test_out_of_credit_pauses_then_switches_and_resumes(models, bus):
    problem = KeyProblem("out_of_credit", "the account is out of credit")
    models.replies["ollama:code"] = ProviderError("openai", "out of credit", problem)
    run = make_run(bus, mode="code")
    thread, results = run_in_thread(run)

    wait_for(lambda: of_type(bus, "decision"))
    decision = of_type(bus, "decision")[0]
    assert decision.data["kind"] == "key_problem" and decision.data["options"] == ["switch", "stop"]
    assert bus.task_status == "paused"
    assert engine.decide("approve") == "Choose one of: switch, stop"
    assert engine.decide("switch") == "Pick a model to switch to"
    assert engine.decide("switch", "ollama:spare") is None
    thread.join(5)

    assert results[0].status == "complete"
    assert "ollama:spare" in models.refs
    assert run.steps["coder"][0].model == "ollama:spare"


def test_stop_at_a_paused_decision(models, bus):
    models.replies["ollama:code"] = ProviderError("openai", "bad key", KeyProblem("invalid", "the API key was rejected"))
    thread, results = run_in_thread(make_run(bus, mode="code"))
    wait_for(lambda: of_type(bus, "decision"))
    assert engine.decide("stop") is None
    thread.join(5)
    assert results[0].status == "stopped"


def test_auto_fallback_switches_to_the_local_model(models, bus):
    agents = {**CREW, "Coder": {**CREW["Coder"], "model": "openai:gpt-6.1-sol"}}
    models.replies["openai:gpt-6.1-sol"] = ProviderError("openai", "no key", KeyProblem("missing", "no API key is set"))
    settings = make_settings(agents, auto_fallback=True, fallback_model="ollama:fallback")
    result = make_run(bus, mode="code", settings=settings).execute()
    assert result.status == "complete"
    assert "ollama:fallback" in models.refs
    assert of_type(bus, "decision") == []


def test_privacy_mode_refuses_cloud_crews_before_any_call(models, bus):
    agents = {**CREW, "Docs": {**CREW["Docs"], "model": "google:gemini-3.8-flash"}}
    result = make_run(bus, settings=make_settings(agents, privacy_mode=True)).execute()
    assert result.status == "error"
    assert "Privacy Mode" in of_type(bus, "error")[0].content
    assert models.calls == []


def test_privacy_mode_refuses_switching_to_the_cloud(models, bus):
    models.replies["ollama:code"] = ProviderError("ollama", "x", KeyProblem("invalid", "rejected"))
    thread, _results = run_in_thread(make_run(bus, mode="code", settings=make_settings(privacy_mode=True)))
    wait_for(lambda: of_type(bus, "decision"))
    assert "Privacy Mode" in engine.decide("switch", "openai:gpt-6.1-sol")
    assert engine.decide("stop") is None
    thread.join(5)


def test_plan_approval_checkpoint(models, bus):
    thread, results = run_in_thread(make_run(bus, mode="code", approve_plan=True))
    wait_for(lambda: of_type(bus, "decision"))
    assert of_type(bus, "decision")[0].data["kind"] == "plan_approval"
    assert models.refs == ["ollama:plan"]
    assert engine.decide("approve") is None
    thread.join(5)
    assert results[0].status == "complete"
    assert models.refs[-1] == "ollama:review"


def test_user_can_revise_the_plan_before_approving(models, bus):
    models.replies["ollama:plan"] = ["Plan v1 with SQLite", "Plan v2 with Postgres"]
    thread, results = run_in_thread(make_run(bus, mode="code", approve_plan=True))
    wait_for(lambda: of_type(bus, "decision"))
    assert of_type(bus, "decision")[0].data["options"] == ["approve", "revise", "stop"]
    assert engine.decide("revise") == "Say what to change in the plan"
    assert engine.decide("revise", message="Use Postgres instead") is None

    wait_for(lambda: len(of_type(bus, "decision")) == 2)  # asked again with the revised plan
    revise_call = models.calls[1]
    assert revise_call[0] == "ollama:plan"
    assert "Use Postgres instead" in revise_call[1][1]["content"]
    assert "Revise your plan" in revise_call[1][0]["content"]
    assert [m.content for m in of_type(bus, "user")] == ["Use Postgres instead"]
    assert engine.decide("approve") is None
    thread.join(5)

    assert results[0].status == "complete"
    assert "Plan v2 with Postgres" in models.calls[2][1][1]["content"]  # the coder gets the revised plan


def test_rejected_plan_stops(models, bus):
    thread, results = run_in_thread(make_run(bus, mode="code", approve_plan=True))
    wait_for(lambda: of_type(bus, "decision"))
    engine.decide("stop")
    thread.join(5)
    assert results[0].status == "stopped"
    assert models.refs == ["ollama:plan"]


def test_low_quota_warning_is_published_once(monkeypatch, bus):
    def stream(ref, messages, **kwargs):
        yield "ok"
        yield Usage(1, 1, 0.0, ["requests: 1 of 100 left in this window"])

    monkeypatch.setattr(providers, "stream", stream)
    make_run(bus, mode="code").execute()
    assert len([m for m in of_type(bus, "warning") if "running low" in m.content]) == 1


def test_provider_errors_are_redacted(monkeypatch, bus):
    def stream(ref, messages, **kwargs):
        raise ProviderError("openai", "boom with sk-live-secretsecret9999")
        yield

    monkeypatch.setattr(providers, "stream", stream)
    assert make_run(bus, mode="plan").execute().status == "error"
    error = of_type(bus, "error")[0].content
    assert "secretsecret" not in error and "••••9999" in error


# ─── Allowances and the task API ─────────────────────────────


def spend(project_id, run_id, provider, usd):
    store.save_message(project_id, run_id, {"agent_name": "Coder", "content": "x", "model": f"{provider}:m", "cost_usd": usd})


def test_allowance_report(client):
    pid = store.create_project("P")["id"]
    run_id = store.create_run(pid, "p", "full")
    spend(pid, run_id, "openai", 8.5)
    spend(pid, run_id, "anthropic", 10.0)
    crew = engine.build_crew(
        make_settings({"A": {"role": "coder", "model": "openai:x"}, "B": {"role": "reviewer", "model": "anthropic:y"}})
    )
    settings = make_settings(allowances={"openai": 10.0, "anthropic": 10.0})
    warnings, blocked = engine.allowance_report(crew, settings)
    assert warnings == ["openai has used $8.50 of its $10.00 monthly allowance"]
    assert blocked == ["anthropic has used $10.00 of its $10.00 monthly allowance"]


def test_used_up_allowance_blocks_new_runs_unless_overridden(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    spend(pid, store.create_run(pid, "old", "full"), "openai", 20.0)
    store.finish_run(store.get_runs(pid)[0]["id"], "complete")
    client.put("/api/settings/run", json={"allowances": {"openai": 20.0}}, headers=AUTH)
    client.put("/api/settings/agents", json={"Coder": {"model": "openai:gpt-6.1-sol"}}, headers=AUTH)

    r = client.post("/api/task", json={"prompt": "x", "project_id": pid}, headers=AUTH)
    assert r.status_code == 409 and "allowance" in r.json()["detail"]
    r = client.post("/api/task", json={"prompt": "x", "project_id": pid, "ignore_allowance": True}, headers=AUTH)
    assert r.status_code == 202
    assert fake_engine.done.wait(5)


def test_stop_and_decision_routes_without_a_task(client):
    assert client.post("/api/task/stop", headers=AUTH).status_code == 409
    r = client.post("/api/task/decision", json={"action": "stop"}, headers=AUTH)
    assert r.status_code == 409 and r.json()["detail"] == "No task is running"


def test_task_route_passes_request_options_to_the_run(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    body = {"prompt": "x", "project_id": pid, "mode": "code", "max_cycles": 5, "approve_plan": True}
    assert client.post("/api/task", json=body, headers=AUTH).status_code == 202
    assert fake_engine.done.wait(5)
    (run,) = fake_engine.calls
    assert (run.mode, run.max_cycles, run.approve_plan) == ("code", 5, True)
    assert [a.name for a in run.agents] == ["PlannerResearcher", "Coder", "ReviewerSecurity"]


def test_review_task_gets_the_latest_runs_output(client, fake_engine):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    first = store.create_run(pid, "build", "full")
    store.save_message(pid, first, {"agent_name": "Coder", "content": "def f(): pass"})
    store.finish_run(first, "complete")
    assert client.post("/api/task", json={"prompt": "check", "project_id": pid, "mode": "review"}, headers=AUTH).status_code == 202
    assert fake_engine.done.wait(5)
    assert "def f(): pass" in fake_engine.calls[0].review_source


def test_chunks_are_live_only():
    bus = MessageBus()
    saved = []
    bus.set_persister(lambda pid, rid, msg: saved.append(msg["message_type"]))
    bus.start_run("p", 1)
    from juli.bus import AgentMessage

    bus.publish(AgentMessage("Coder", "par", message_type="chunk"))
    bus.publish(AgentMessage("Coder", "partial", message_type="agent"))
    assert saved == ["agent"]
    assert [m.message_type for m in bus.history] == ["agent"]


def test_paused_run_blocks_new_tasks():
    bus = MessageBus()
    assert bus.try_begin_task("t", "p1")
    bus.set_task_status("paused")
    assert not bus.try_begin_task("t2", "p2")
    assert bus.set_active_project("p2") is False


# ─── Crew discussion and the user's notes ────────────────────


def test_discussion_is_off_by_default(models, bus):
    make_run(bus, mode="code").execute()
    assert models.refs == ["ollama:plan", "ollama:code", "ollama:review"]


def test_discussion_revises_until_the_crew_agrees(models, bus):
    models.replies.update(
        {
            "ollama:plan": ["Plan v1", "Plan v2"],
            "ollama:code": ["Needs an index.\nPLAN: CHANGES NEEDED", "PLAN: AGREED", "the code"],
            "ollama:review": ["PLAN: AGREED", "PLAN: AGREED", APPROVED],
        }
    )
    result = make_run(bus, mode="code", discussion_rounds=3).execute()

    assert result.status == "complete"
    assert models.refs == [
        "ollama:plan",  # plan
        "ollama:code",
        "ollama:review",
        "ollama:plan",  # round 1: feedback, then revise
        "ollama:code",
        "ollama:review",  # round 2: all agree
        "ollama:code",
        "ollama:review",  # code and review as usual
    ]
    discuss_call = models.calls[1]
    assert "PLAN: AGREED" in discuss_call[1][0]["content"] and "path=" not in discuss_call[1][0]["content"]
    assert "Needs an index." in models.calls[2][1][1]["content"]  # the reviewer sees this round's feedback
    assert "Needs an index." in models.calls[3][1][1]["content"]  # the planner revises from it
    assert "Plan v2" in models.calls[6][1][1]["content"]  # coding starts from the agreed plan
    assert any("agreed on the plan after 2" in m.content for m in of_type(bus, "system"))


def test_discussion_stops_after_its_rounds(models, bus):
    models.replies.update({"ollama:code": "PLAN: CHANGES NEEDED", "ollama:review": "PLAN: CHANGES NEEDED"})
    make_run(bus, mode="code", discussion_rounds=1, max_cycles=1).execute()
    assert models.refs[:4] == ["ollama:plan", "ollama:code", "ollama:review", "ollama:plan"]
    assert any("Discussion ended after 1" in m.content for m in of_type(bus, "system"))


def test_discussion_rounds_come_from_settings(models, bus):
    models.replies.update({"ollama:code": ["PLAN: AGREED", "code"], "ollama:review": ["PLAN: AGREED", APPROVED]})
    make_run(bus, mode="code", settings=make_settings(discussion_rounds=2)).execute()
    assert models.refs == ["ollama:plan", "ollama:code", "ollama:review", "ollama:code", "ollama:review"]


def test_user_notes_reach_every_later_turn(models, bus):
    run = make_run(bus, mode="code")
    models.on_chunk = lambda: run.say("Use Postgres") if len(models.calls) == 1 and not of_type(bus, "user") else None
    assert run.execute().status == "complete"
    briefs = [messages[1]["content"] for _, messages, _ in models.calls]
    assert "Use Postgres" not in briefs[0]
    assert all("Notes from the user" in b and "Use Postgres" in b for b in briefs[1:])
    assert [m.agent_name for m in of_type(bus, "user")] == ["You"]


def test_message_route_reaches_the_running_task(client, models):
    models.on_chunk = lambda: time.sleep(0.02)
    models.replies["ollama:code"] = " ".join(["slow"] * 100)
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    client.put(
        "/api/settings/agents", json={k: {"model": v["model"], "role": v.get("role", "custom")} for k, v in CREW.items()}, headers=AUTH
    )
    assert client.post("/api/task/message", json={"content": "hi"}, headers=AUTH).status_code == 409
    assert client.post("/api/task", json={"prompt": "x", "project_id": pid, "mode": "plan"}, headers=AUTH).status_code == 202
    wait_for(lambda: engine._active is not None)
    assert client.post("/api/task/message", json={"content": "Keep it small"}, headers=AUTH).status_code == 200
    client.post("/api/task/stop", headers=AUTH)
    wait_for(lambda: engine._active is None)


# ─── Follow-up chat ──────────────────────────────────────────


def finished_run(pid):
    run_id = store.create_run(pid, "Build a todo app", "full")
    store.save_message(pid, run_id, {"agent_name": "Coder", "content": "CREATE TABLE todos (id INT);", "message_type": "agent"})
    store.finish_run(run_id, "complete")
    return run_id


def test_follow_up_chat_keeps_a_thread(client, models):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = finished_run(pid)
    models.replies["ollama:qwen3:8b"] = ["Because it is simple.", "Add a done column."]

    r = client.post(f"/api/runs/{run_id}/chat", json={"agent": "Coder", "message": "Why this schema?"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["reply"].strip() == "Because it is simple."
    assert r.json()["model"] == "ollama:qwen3:8b" and r.json()["cost_usd"] == 0.0
    first = models.calls[0][1]
    assert "CREATE TABLE todos" in first[1]["content"] and "Why this schema?" in first[1]["content"]
    assert "follow-up questions" in first[0]["content"]

    client.post(f"/api/runs/{run_id}/chat", json={"agent": "Coder", "message": "What next?"}, headers=AUTH)
    second = models.calls[1][1]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    assert second[2]["content"].strip() == "Because it is simple." and second[3]["content"] == "What next?"

    types = [m["message_type"] for m in store.run_messages(run_id)]
    assert types == ["agent", "question", "answer", "question", "answer"]
    assert engine.review_source(pid) == "### Coder\n\nCREATE TABLE todos (id INT);"  # answers aren't output


def test_follow_up_errors(client, models):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    assert client.post("/api/runs/999/chat", json={"agent": "Coder", "message": "q"}, headers=AUTH).status_code == 404
    running = store.create_run(pid, "p", "full")
    assert client.post(f"/api/runs/{running}/chat", json={"agent": "Coder", "message": "q"}, headers=AUTH).status_code == 409
    run_id = finished_run(pid)
    assert client.post(f"/api/runs/{run_id}/chat", json={"agent": "Nobody", "message": "q"}, headers=AUTH).status_code == 404

    models.replies["ollama:qwen3:8b"] = ProviderError("ollama", "can't reach Ollama at http://localhost:11434")
    r = client.post(f"/api/runs/{run_id}/chat", json={"agent": "Coder", "message": "q"}, headers=AUTH)
    assert r.status_code == 502 and "Ollama" in r.json()["detail"]
    assert [m["message_type"] for m in store.run_messages(run_id)] == ["agent"]  # failed questions aren't stored


def test_follow_up_respects_privacy_mode(client, monkeypatch):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = finished_run(pid)
    client.put("/api/settings/agents", json={"Coder": {"model": "openai:gpt-6.1-sol"}}, headers=AUTH)
    client.put("/api/settings/run", json={"privacy_mode": True}, headers=AUTH)
    r = client.post(f"/api/runs/{run_id}/chat", json={"agent": "Coder", "message": "q"}, headers=AUTH)
    assert r.status_code == 409 and "Privacy Mode" in r.json()["detail"]


def test_follow_up_that_would_pass_a_cap_is_not_sent(client, models):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = finished_run(pid)
    client.put("/api/settings/run", json={"token_cap": 10}, headers=AUTH)
    r = client.post(f"/api/runs/{run_id}/chat", json={"agent": "Coder", "message": "Why this schema?"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["detail"] == "The question wasn't sent: the token cap of 10 tokens was reached. Raise the cap in Settings to ask it."
    assert models.calls == []
    assert [m["message_type"] for m in store.run_messages(run_id)] == ["agent"]


def test_follow_up_cut_short_by_a_cap_keeps_the_answer_so_far(client, models):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = finished_run(pid)
    settings = make_settings()
    models.replies["ollama:plan"] = "one two three four five six seven eight nine ten"
    engine.follow_up(store.get_run(run_id), "Planner", "q", settings)  # no cap: the whole answer
    sent = engine.harness.estimate(models.calls[0][1])

    # Each question counts on its own: the first one's tokens don't use up this cap.
    capped = make_settings(token_cap=sent + 20)
    answer = engine.follow_up(store.get_run(run_id), "Planner", "And again?", capped)
    assert answer["reply"].startswith("one two") and "ten" not in answer["reply"]
    assert answer["notice"] == f"The answer stops here: the token cap of {sent + 20:,} tokens was reached."
    assert answer["tokens_in"] > 0 and answer["tokens_out"] > 0 and answer["cost_usd"] == 0.0
    stored = store.run_messages(run_id)[-3:]
    assert [m["message_type"] for m in stored] == ["question", "answer", "limit_reached"]
    assert stored[1]["content"] == answer["reply"] and stored[2]["content"] == answer["notice"]
    assert stored[2]["agent_name"] == "Planner"  # with its answer when the view shows only the Planner


def test_follow_up_on_a_priced_model_stops_at_the_budget_cap(client, models):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = finished_run(pid)
    # 4000 output tokens at $10 per million would cost $0.04.
    agents = {"Coder": {"role": "coder", "model": "openai:gpt-6.1-sol", "prompt": "Code it.", "max_tokens": 4000}}
    with pytest.raises(engine.Stopped, match=r"the budget cap of \$0\.01 was reached"):
        engine.follow_up(store.get_run(run_id), "Coder", "q", make_settings(agents, budget_usd=0.01))
    assert models.calls == []


def test_follow_up_warns_when_the_budget_cap_cannot_count_the_model(client, models):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = finished_run(pid)
    agents = {"Coder": {"role": "coder", "model": "openai:not-in-the-price-list", "prompt": "Code it."}}
    warning = "openai:not-in-the-price-list has no known price, so the budget cap can't count its cost. Set a token cap to limit it."

    answer = engine.follow_up(store.get_run(run_id), "Coder", "q", make_settings(agents, budget_usd=0.01))
    assert answer["warnings"] == [warning] and answer["cost_usd"] is None and answer["notice"] is None
    stored = store.run_messages(run_id)[-3:]
    assert [(m["message_type"], m["agent_name"]) for m in stored] == [("question", "You"), ("answer", "Coder"), ("warning", "Coder")]
    assert stored[2]["content"] == warning

    # No budget cap, or a model it can count: nothing to warn about.
    assert engine.follow_up(store.get_run(run_id), "Coder", "q", make_settings(agents))["warnings"] == []
    assert engine.follow_up(store.get_run(run_id), "Planner", "q", make_settings(budget_usd=0.01))["warnings"] == []


# ─── turn_start ──────────────────────────────────────────────


def test_turn_start_comes_before_each_turns_text(models, bus):
    make_run(bus, mode="code").execute()
    starts = of_type(bus, "turn_start")
    assert [(m.agent_name, m.model, m.data) for m in starts] == [
        ("Planner", "ollama:plan", {"role": "planner", "activity": "planning"}),
        ("Coder", "ollama:code", {"role": "coder", "activity": "coding"}),
        ("Reviewer", "ollama:review", {"role": "reviewer", "activity": "reviewing"}),
    ]
    assert starts[1].content == "Coder is coding…"
    kinds = [m.message_type for m in bus.events if m.agent_name == "Coder"]
    assert kinds[0] == "turn_start" and kinds[1] == "chunk" and kinds[-1] == "agent"


def test_turn_start_names_discussion_and_revision(models, bus):
    models.replies.update({"ollama:code": ["PLAN: CHANGES NEEDED", "code"], "ollama:review": ["PLAN: AGREED", APPROVED]})
    make_run(bus, mode="code", discussion_rounds=1).execute()
    activities = [m.data["activity"] for m in of_type(bus, "turn_start")]
    assert activities[:4] == ["planning", "discussing the plan", "discussing the plan", "revising the plan"]


def test_turn_start_again_after_switching_model(models, bus):
    models.replies["ollama:code"] = ProviderError("openai", "bad key", KeyProblem("invalid", "the API key was rejected"))
    thread, _results = run_in_thread(make_run(bus, mode="code"))
    wait_for(lambda: of_type(bus, "decision"))
    engine.decide("switch", "ollama:spare")
    thread.join(5)
    coder_starts = [m.model for m in of_type(bus, "turn_start") if m.agent_name == "Coder"]
    assert coder_starts == ["ollama:code", "ollama:spare"]


def test_turn_start_is_live_but_not_stored():
    bus = MessageBus()
    saved = []
    bus.set_persister(lambda pid, rid, msg: saved.append(msg["message_type"]))
    bus.start_run("p", 1)
    from juli.bus import AgentMessage

    bus.publish(AgentMessage("Coder", "Coder is coding…", message_type="turn_start"))
    assert saved == []
    assert [m.message_type for m in bus.history] == ["turn_start"]
