import json

from typer.testing import CliRunner

from juli import cli, config, keystore, roles
from juli.local import ollama

from .conftest import fixture_json, fixture_text, serve

NDJSON = {"content-type": "application/x-ndjson"}


def invoke(*args, **kwargs):
    result = CliRunner().invoke(cli.app, list(args), **kwargs)
    result.text = " ".join(result.output.split())  # rich wraps long lines
    return result


def test_hardware(laptop):
    result = invoke("hardware")
    assert result.exit_code == 0
    assert "i5-1135G7" in result.output and "none (models run on the CPU)" in result.output
    assert laptop["fingerprint"] in result.output


def test_catalogue_shows_fit_and_licenses(laptop):
    result = invoke("models", "catalogue")
    assert result.exit_code == 0
    assert "qwen3:8b" in result.output and "cannot" in result.output and "(accept)" in result.output


def test_models_list_and_offline_message(net, laptop):
    result = invoke("models", "list")
    assert result.exit_code == 1 and "ollama serve" in result.output
    net.handler = serve(
        {("GET", "/api/tags"): (200, fixture_json("ollama_tags.json"), {}), ("GET", "/api/ps"): (200, fixture_json("ollama_ps.json"), {})}
    )
    result = invoke("models", "list")
    assert result.exit_code == 0 and "Q4_K_M" in result.output and "yes" in result.output


def test_pull_asks_for_the_license_first(net):
    net.handler = serve({("POST", "/api/pull"): (200, fixture_text("ollama_pull.ndjson"), NDJSON)})
    declined = invoke("models", "pull", "gemma3:1b", input="n\n")
    assert declined.exit_code == 1 and "Gemma Terms of Use" in declined.output
    assert not net.requests and "gemma" not in (config.load_settings().get("licenses") or {})

    accepted = invoke("models", "pull", "gemma3:1b", input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert "gemma3:1b is installed" in accepted.output
    assert "gemma" in config.load_settings()["licenses"]


def test_pull_without_a_license_prompt(net):
    net.handler = serve({("POST", "/api/pull"): (200, fixture_text("ollama_pull.ndjson"), NDJSON)})
    result = invoke("models", "pull", "qwen3:8b")
    assert result.exit_code == 0 and "Do you accept" not in result.output


def test_rm_asks_first(net):
    net.handler = serve({("DELETE", "/api/delete"): (200, "", {})})
    assert invoke("models", "rm", "qwen3:8b", input="n\n").exit_code == 1
    assert not net.requests
    assert invoke("models", "rm", "qwen3:8b", "--yes").exit_code == 0
    assert json.loads(net.requests[0].content) == {"model": "qwen3:8b"}


def test_bench(net, laptop):
    net.handler = serve({("POST", "/api/generate"): (200, fixture_json("ollama_generate.json"), {})})
    result = invoke("models", "bench", "qwen3:8b")
    assert result.exit_code == 0 and "7.0 tok/s" in result.output


def test_auto_crew_preview_and_apply(laptop):
    preview = invoke("auto-crew")
    assert preview.exit_code == 0 and "ollama:qwen3:14b" in preview.output and "--apply" in preview.output
    assert "Gemma Terms of Use" in preview.output
    assert config.load_settings()["agents"]["Coder"]["model"] == roles.DEFAULT_MODEL
    applied = invoke("auto-crew", "--agent", "Coder", "--apply")
    assert applied.exit_code == 0
    settings = config.load_settings()
    assert settings["agents"]["Coder"]["model"] == "ollama:qwen3:14b"
    assert settings["agents"]["DocsDiagram"]["model"] == roles.DEFAULT_MODEL


def test_mode(laptop):
    assert "Mode: custom" in invoke("mode").output
    result = invoke("mode", "hybrid", "--cloud-model", "anthropic:claude-sonnet-5-5")
    assert result.exit_code == 0 and "go to anthropic" in result.text
    assert "Mode: hybrid" in invoke("mode").output
    assert invoke("mode", "hybrid", "--cloud-model", "ollama:qwen3:8b").exit_code == 1


def test_endpoint_add_and_rm(net, memory_keyring):
    net.handler = lambda req: (200, {"object": "list", "data": [{"id": "qwen3-8b", "object": "model", "created": 1, "owned_by": "me"}]}, {})
    result = invoke("endpoint", "add", "lmstudio", "http://localhost:1234/v1", "--with-key", input="sk-test-not-a-real-key-1234\n")
    assert result.exit_code == 0 and "lmstudio:qwen3-8b" in result.output
    assert "sk-test-not-a-real-key-1234" not in result.output.replace("API key:", "")
    assert keystore.get_key("lmstudio") == "sk-test-not-a-real-key-1234"
    assert invoke("endpoint", "add", "Bad Id", "http://localhost:1/v1").exit_code == 1
    assert invoke("endpoint", "rm", "lmstudio").exit_code == 0
    assert invoke("endpoint", "rm", "lmstudio").exit_code == 1


def test_pull_progress_never_reaches_stored_history(monkeypatch):
    saved = []
    from juli.bus import AgentMessage, message_bus

    message_bus.set_persister(lambda project_id, run_id, msg: saved.append(msg))
    message_bus.active_project_id = "p1"
    try:
        message_bus.publish(AgentMessage("System", "qwen3:8b: 50%", message_type="pull_progress", data={"model": "qwen3:8b"}))
    finally:
        message_bus.set_persister(None)
    assert saved == [] and message_bus.history == []
    assert ollama.PULLS.list() == []


def test_a_license_that_cant_be_recorded_is_a_message_not_a_traceback(net):
    result = invoke("models", "pull", "Qwen3:8b", input="y\n")  # "model:Qwen3" isn't a valid license id
    assert result.exit_code == 1 and not isinstance(result.exception, ValueError)
    assert "Unknown license" in result.output
    assert not net.requests
