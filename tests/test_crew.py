import pytest

from juli import config, engine, providers, roles
from juli.local import crew

from .conftest import AUTH

CREW = {
    "PlannerResearcher": "planner",
    "Coder": "coder",
    "ReviewerSecurity": "reviewer",
    "DevOps": "custom",
    "TestMonitor": "tester",
    "DocsDiagram": "docs",
}


def machine(ram_gb: float, vram_gb: float | None = None, disk_gb: float | None = 500) -> dict:
    gpu = {"vendor": "nvidia", "name": "GPU", "vram_gb": vram_gb, "unified": False} if vram_gb else None
    return {"ram_gb": ram_gb, "gpu": gpu, "disk_free_gb": disk_gb}


def models(result: dict) -> dict:
    return {name: pick and pick["model"] for name, pick in result["agents"].items()}


# ─── Auto-Crew ───────────────────────────────────────────────


def test_cpu_laptop_gets_the_strongest_models_that_fit_in_ram(laptop):
    result = crew.auto_crew(laptop, set(), CREW)
    assert models(result) == {
        "PlannerResearcher": "ollama:deepseek-r1:14b",
        "Coder": "ollama:qwen3:14b",
        "ReviewerSecurity": "ollama:qwen3:14b",
        "DevOps": "ollama:qwen3:14b",  # custom roles get general models
        "TestMonitor": "ollama:qwen3:14b",  # no tester model fits, so the best general one
        "DocsDiagram": "ollama:gemma3:4b",
    }
    assert all(pick["tier"] == "slow" for pick in result["agents"].values())
    assert result["agents"]["Coder"]["num_ctx"] == 8192
    assert result["downloads"] == ["deepseek-r1:14b", "gemma3:4b", "qwen3:14b"]
    assert result["download_gb"] == pytest.approx(21.7)
    assert result["shared"] is False
    assert result["fallback_model"] == "ollama:qwen3:14b"


def test_a_big_gpu_gets_great_tier_specialists():
    result = crew.auto_crew(machine(32, vram_gb=24), set(), CREW)
    picks = models(result)
    assert picks["Coder"] == "ollama:qwen3-coder:30b"
    assert picks["TestMonitor"] == "ollama:qwen3-coder:30b"
    assert picks["PlannerResearcher"] == "ollama:deepseek-r1:32b"
    assert all(pick["tier"] == "great" for pick in result["agents"].values())


def test_great_tier_beats_a_bigger_slow_model():
    pick = crew.auto_crew(machine(64, vram_gb=8), set(), {"Coder": "coder"})["agents"]["Coder"]
    assert pick["model"] == "ollama:qwen3:8b" and pick["tier"] == "great"


def test_ties_go_to_installed_models(laptop):
    assert models(crew.auto_crew(laptop, set(), {"R": "reviewer"}))["R"] == "ollama:qwen3:14b"
    picked = crew.auto_crew(laptop, {"deepseek-r1:14b"}, {"R": "reviewer"})["agents"]["R"]
    assert picked["model"] == "ollama:deepseek-r1:14b" and picked["installed"] is True


def test_one_shared_model_when_the_downloads_dont_fit_on_disk():
    result = crew.auto_crew(machine(16, disk_gb=12), set(), CREW)
    assert set(models(result).values()) == {"ollama:qwen3:14b"}
    assert result["shared"] is True and result["downloads"] == ["qwen3:14b"]


def test_nothing_fits_a_tiny_machine():
    result = crew.auto_crew(machine(1), set(), {"Coder": "coder"})
    assert result["agents"] == {"Coder": None}
    assert result["fallback_model"] is None
    assert result["warnings"] == ["No catalogue model fits this machine for Coder"]


def test_auto_crew_route_previews_without_saving(client, laptop):
    before = config.load_settings()
    r = client.post("/api/local/auto-crew", json={}, headers=AUTH)
    assert r.status_code == 200 and r.json()["applied"] == []
    assert [lic["id"] for lic in r.json()["licenses"]] == ["gemma"]  # gemma3:4b for the docs
    assert config.load_settings()["agents"] == before["agents"]


def test_auto_crew_changes_only_the_agents_asked_for(client, laptop):
    client.put("/api/settings/agents", json={"Coder": {"prompt": "My own prompt."}}, headers=AUTH)
    r = client.post("/api/local/auto-crew", json={"agents": ["Coder"], "apply": True, "set_fallback": True}, headers=AUTH)
    assert r.json()["applied"] == ["Coder"]
    settings = config.load_settings()
    coder = settings["agents"]["Coder"]
    assert coder["model"] == "ollama:qwen3:14b" and coder["num_ctx"] == 8192
    assert coder["prompt"] == "My own prompt."  # user edits are kept
    assert settings["agents"]["PlannerResearcher"]["model"] == roles.DEFAULT_MODEL
    assert settings["run"]["fallback_model"] == "ollama:qwen3:14b"
    # The engine passes num_ctx on to Ollama.
    assert next(a for a in engine.build_crew(settings) if a.name == "Coder").num_ctx == 8192


def test_auto_crew_unknown_agent(client, laptop):
    assert client.post("/api/local/auto-crew", json={"agents": ["Nobody"]}, headers=AUTH).status_code == 422


def test_changing_an_agents_model_drops_its_fitted_context(client, laptop):
    client.post("/api/local/auto-crew", json={"agents": ["Coder"], "apply": True}, headers=AUTH)
    client.put("/api/settings/agents", json={"Coder": {"prompt": "Still fitted."}}, headers=AUTH)
    assert config.load_settings()["agents"]["Coder"]["num_ctx"] == 8192
    client.put("/api/settings/agents", json={"Coder": {"model": "ollama:qwen3:4b"}}, headers=AUTH)
    assert "num_ctx" not in config.load_settings()["agents"]["Coder"]


# ─── Modes ───────────────────────────────────────────────────

SONNET = "anthropic:claude-sonnet-5-5"


def test_current_mode():
    settings = config.default_settings()
    assert crew.current_mode(settings) == "custom"  # all local, but not enforced
    settings["run"]["privacy_mode"] = True
    assert crew.current_mode(settings) == "privacy"
    settings["run"]["privacy_mode"] = False
    for name in ("PlannerResearcher", "ReviewerSecurity"):
        settings["agents"][name]["model"] = SONNET
    assert crew.current_mode(settings) == "hybrid"
    settings["agents"]["Coder"]["model"] = SONNET
    assert crew.current_mode(settings) == "custom"
    for agent in settings["agents"].values():
        agent["model"] = SONNET
    assert crew.current_mode(settings) == "cloud"


def test_hybrid_moves_plan_and_review_to_the_cloud(client, laptop):
    r = client.put("/api/settings/mode", json={"mode": "hybrid", "cloud_model": SONNET}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["changed"] == {"PlannerResearcher": SONNET, "ReviewerSecurity": SONNET}
    assert "go to anthropic" in body["notice"] and "Privacy Mode keeps everything" in body["notice"]
    assert body["warnings"] == ["No API key is set for anthropic yet"]
    settings = config.load_settings()
    assert settings["agents"]["Coder"]["model"] == roles.DEFAULT_MODEL  # local agents stay as they are
    assert client.get("/api/settings", headers=AUTH).json()["mode"] == "hybrid"


def test_cloud_then_privacy(client, laptop, memory_keyring):
    memory_keyring.set_password("juli", "anthropic", "sk-ant-not-a-real-key-1234")
    body = client.put("/api/settings/mode", json={"mode": "cloud", "cloud_model": SONNET}, headers=AUTH).json()
    assert len(body["changed"]) == 6 and body["warnings"] == []
    assert client.get("/api/settings/mode", headers=AUTH).json() == {"mode": "cloud"}

    body = client.put("/api/settings/mode", json={"mode": "privacy"}, headers=AUTH).json()
    assert body["notice"] == ""
    settings = config.load_settings()
    assert settings["run"]["privacy_mode"] is True
    assert settings["agents"]["Coder"]["model"] == "ollama:qwen3:14b"  # Auto-Crew picks
    assert settings["agents"]["Coder"]["num_ctx"] == 8192
    assert all(providers.is_local(a["model"]) for a in settings["agents"].values())
    assert crew.current_mode(settings) == "privacy"


def test_privacy_mode_is_enforced_in_providers_after_switching(client, laptop):
    client.put("/api/settings/mode", json={"mode": "privacy"}, headers=AUTH)
    settings = config.load_settings()
    run = engine.Run("hi", "full", engine.build_crew(settings), settings=settings)
    assert run.model_problem(SONNET) == f"Privacy Mode is on: {SONNET} is a cloud model"
    with pytest.raises(providers.PrivacyViolation):
        next(providers.stream(SONNET, [{"role": "user", "content": "hi"}], privacy=settings["run"]["privacy_mode"]))


def test_hybrid_needs_a_cloud_model_for_local_planners(client, laptop):
    r = client.put("/api/settings/mode", json={"mode": "hybrid"}, headers=AUTH)
    assert r.status_code == 422 and "PlannerResearcher" in r.json()["detail"]
    r = client.put("/api/settings/mode", json={"mode": "cloud", "cloud_model": "ollama:qwen3:8b"}, headers=AUTH)
    assert r.status_code == 422 and "runs locally" in r.json()["detail"]
    assert client.put("/api/settings/mode", json={"mode": "offline"}, headers=AUTH).status_code == 422


def test_hybrid_keeps_cloud_models_the_user_chose(client, laptop):
    client.put("/api/settings/agents", json={"PlannerResearcher": {"model": "openai:gpt-6.1-sol"}, "ReviewerSecurity": {"model": SONNET}}, headers=AUTH)
    body = client.put("/api/settings/mode", json={"mode": "hybrid"}, headers=AUTH).json()
    assert body["changed"] == {}
    assert "openai" in body["notice"] and "anthropic" in body["notice"]


def test_nothing_fits_falls_back_to_the_default_model_with_a_warning():
    settings = config.default_settings()
    for agent in settings["agents"].values():
        agent["model"] = SONNET
    result = crew.set_mode(settings, "privacy", None, lambda agents: {name: None for name in agents})
    assert all(a["model"] == roles.DEFAULT_MODEL for a in settings["agents"].values())
    assert len(result["warnings"]) == 6


def test_switching_warns_about_models_that_still_need_downloading():
    settings = config.default_settings()
    for name in ("Coder", "DocsDiagram"):
        settings["agents"][name]["model"] = SONNET
    picks = {
        "Coder": {"model": "ollama:qwen3:14b", "num_ctx": 8192, "installed": False},
        "DocsDiagram": {"model": "ollama:qwen3:8b", "num_ctx": 40960, "installed": True},
    }
    result = crew.set_mode(settings, "privacy", None, lambda agents: picks)
    assert result["warnings"] == ["Coder now uses ollama:qwen3:14b, which isn't downloaded yet; download it before a run"]
