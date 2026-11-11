import json

from typer.testing import CliRunner

from juli import cli, config, engine, roles, store

from .conftest import AUTH


def write_settings(data):
    config.settings_path().write_text(json.dumps(data), encoding="utf-8")


def test_legacy_model_keys_migrate_in_place_keeping_edits():
    write_settings(
        {
            "agents": {
                "Coder": {"model": "claude", "prompt": "My own coder prompt", "color": "#123456"},
                "DocsDiagram": {"model": "gemini_flash", "job_title": "Scribe"},
                "Custom": {"model": "ollama:qwen3:8b", "prompt": "Mine"},
            },
            "providers": ["openai"],
            "available_models": ["gpt4", "claude", "gemini", "gemini_flash", "ollama:qwen3:8b"],
        }
    )
    config.migrate_legacy_settings()

    saved = json.loads(config.settings_path().read_text(encoding="utf-8"))
    assert saved["agents"] == {
        "Coder": {"model": "anthropic:claude-opus-5-5", "prompt": "My own coder prompt", "color": "#123456"},
        "DocsDiagram": {"model": "google:gemini-3.8-flash", "job_title": "Scribe"},
        "Custom": {"model": "ollama:qwen3:8b", "prompt": "Mine"},
    }
    assert saved["available_models"] == [
        "openai:gpt-6.1-sol",
        "anthropic:claude-opus-5-5",
        "google:gemini-4-argon",
        "google:gemini-3.8-flash",
        "ollama:qwen3:8b",
    ]
    assert saved["providers"] == ["openai"]


def test_load_settings_migrates_even_before_startup():
    write_settings({"agents": {"PlannerResearcher": {"model": "gpt4"}}})
    settings = config.load_settings()
    assert settings["agents"]["PlannerResearcher"]["model"] == "openai:gpt-6.1-sol"
    assert settings["run"] == {**config.DEFAULT_RUN, "allowances": {}}


def test_every_legacy_key_maps_to_a_verified_preset():
    from juli import providers

    assert set(config.LEGACY_MODEL_REFS.values()) <= set(providers.MODELS)


def test_fresh_install_crew_is_local():
    from juli import providers

    assert all(providers.is_local(m) for m in roles.DEFAULT_AGENT_MODEL_MAP.values())


def test_default_settings_have_roles_and_refs():
    agents = config.default_settings()["agents"]
    assert {a["role"] for a in agents.values()} == {"planner", "coder", "reviewer", "custom", "tester", "docs"}
    assert all(":" in a["model"] for a in agents.values())


def test_settings_api_shows_presets_and_run_settings(client):
    body = client.get("/api/settings", headers=AUTH).json()
    assert "anthropic:claude-haiku-5-5" in body["available_models"]
    assert body["run"]["budget_usd"] is None and body["run"]["token_cap"] is None


def test_run_settings_roundtrip(client):
    run = {
        "budget_usd": 2.5,
        "token_cap": 50000,
        "privacy_mode": True,
        "auto_fallback": True,
        "fallback_model": "ollama:qwen3:8b",
        "discussion_rounds": 2,
        "allowances": {"openai": 20},
        "max_tool_rounds": 40,
        "max_handoffs": 0,
    }
    assert client.put("/api/settings/run", json=run, headers=AUTH).status_code == 200
    assert client.get("/api/settings", headers=AUTH).json()["run"] == {**run, "allowances": {"openai": 20.0}}
    # Empty means no limit again.
    client.put("/api/settings/run", json={}, headers=AUTH)
    assert client.get("/api/settings", headers=AUTH).json()["run"]["budget_usd"] is None


def test_fallback_model_must_be_local(client):
    r = client.put("/api/settings/run", json={"fallback_model": "openai:gpt-6.1-sol"}, headers=AUTH)
    assert r.status_code == 422


def test_agent_max_tokens_can_be_set_and_cleared(client):
    client.put("/api/settings/agents", json={"Coder": {"max_tokens": 2048, "role": "coder"}}, headers=AUTH)
    assert config.load_settings()["agents"]["Coder"]["max_tokens"] == 2048
    client.put("/api/settings/agents", json={"Coder": {"color": "#000000"}}, headers=AUTH)
    assert config.load_settings()["agents"]["Coder"]["max_tokens"] == 2048  # unset fields are kept
    client.put("/api/settings/agents", json={"Coder": {"max_tokens": None}}, headers=AUTH)
    assert config.load_settings()["agents"]["Coder"]["max_tokens"] is None


def test_agents_route_reads_settings(client):
    client.post("/api/settings/agents", json={"name": "Dba", "role": "custom", "model": "ollama:qwen3:8b"}, headers=AUTH)
    agents = {a["name"]: a for a in client.get("/api/agents", headers=AUTH).json()}
    assert agents["Dba"] == {"name": "Dba", "role": "custom", "color": "#6b7280", "icon": "system", "model": "ollama:qwen3:8b"}
    assert agents["DocsDiagram"]["model"] == "ollama:qwen3:8b"


# ─── CLI ─────────────────────────────────────────────────────


def test_cli_has_no_push_option():
    result = CliRunner().invoke(cli.app, ["run", "x", "--push"])
    assert result.exit_code != 0
    assert "push" not in CliRunner().invoke(cli.app, ["run", "--help"]).output.lower()


def test_cli_lists_the_crew_from_settings():
    result = CliRunner().invoke(cli.app, ["agents"])
    assert result.exit_code == 0
    assert "DocsDiagram" in result.output and "qwen3:8b" in result.output


def test_cli_run_stores_the_run(fake_engine, tmp_path):
    result = CliRunner().invoke(cli.app, ["run", "hello", "--code", "--output", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    pid = store.find_or_create_project("CLI")
    (run,) = store.get_runs(pid)
    assert (run["prompt"], run["mode"], run["status"], run["tokens_in"]) == ("hello", "code", "complete", 10)
    assert fake_engine.calls[0].mode == "code"
    assert list((tmp_path / "out").glob("juli_output_*.md"))


def test_cli_review_uses_the_projects_latest_output(fake_engine, tmp_path):
    store.init_db()
    pid = store.find_or_create_project("CLI")
    run_id = store.create_run(pid, "build", "full")
    store.save_message(pid, run_id, {"agent_name": "Coder", "content": "print('hi')"})
    result = CliRunner().invoke(cli.app, ["run", "security", "--review", "--output", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "print('hi')" in fake_engine.calls[0].review_source
    assert engine.review_source(pid).startswith("### Coder")


def test_cli_ctrl_c_at_a_prompt_still_finishes_the_run(monkeypatch, tmp_path):
    import typer

    from juli.bus import AgentMessage

    # Patch Run.execute, not engine.execute, so the run is registered as active
    # and the CLI's engine.stop() really reaches it.
    def execute(run):
        run.bus.publish(AgentMessage("System", "Approve the plan?", message_type="decision", data={"kind": "plan_approval"}))
        cancelled = run.cancel.wait(5)
        return engine.RunResult("stopped" if cancelled else "complete", 3, 2, 0.0)

    def abort(msg):
        raise typer.Abort()

    monkeypatch.setattr(engine.Run, "execute", execute)
    monkeypatch.setattr(cli, "_answer", abort)
    result = CliRunner().invoke(cli.app, ["run", "hello", "--output", str(tmp_path)])

    assert result.exit_code == 0, result.output
    (run,) = store.get_runs(store.find_or_create_project("CLI"))
    assert (run["status"], run["tokens_in"]) == ("stopped", 3) and run["ended_at"]
    assert list(tmp_path.glob("juli_output_*.md"))
