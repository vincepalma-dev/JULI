import json
import threading
import time

import httpx
import pytest

from juli import config, providers, store
from juli.bus import message_bus
from juli.local import ollama

from .conftest import AUTH, fixture_json, fixture_text, serve

NDJSON = {"content-type": "application/x-ndjson"}
LAYERS_TOTAL = 5_225_376_000 + 1723


def wait_for(jobs: ollama.PullJobs, model: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(j for j in jobs.list() if j["model"] == model)
        if job["status"] != "pulling":
            return job
        time.sleep(0.01)
    raise AssertionError(f"{model} still pulling")


def ollama_routes(extra: dict | None = None) -> dict:
    return {
        ("GET", "/api/version"): (200, {"version": "0.20.0"}, {}),
        ("GET", "/api/tags"): (200, fixture_json("ollama_tags.json"), {}),
        ("GET", "/api/ps"): (200, fixture_json("ollama_ps.json"), {}),
        ("POST", "/api/pull"): (200, fixture_text("ollama_pull.ndjson"), NDJSON),
        ("POST", "/api/generate"): (200, fixture_json("ollama_generate.json"), {}),
        **(extra or {}),
    }


# ─── Status, tags, ps ────────────────────────────────────────


def test_version_tags_and_ps(net):
    net.handler = serve(ollama_routes())
    assert ollama.version() == "0.20.0"
    assert [m["name"] for m in ollama.tags()] == ["qwen3:8b", "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M"]
    assert ollama.ps()[0]["name"] == "qwen3:8b"
    assert ollama.installed() == {"qwen3:8b", "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M"}
    assert str(net.requests[0].url) == "http://localhost:11434/api/version"


def test_offline_ollama(net):
    assert ollama.status() == {"running": False, "version": None, "base_url": "http://localhost:11434"}
    assert ollama.installed() == set()
    with pytest.raises(httpx.HTTPError):
        ollama.tags()


def test_a_custom_ollama_base_url_is_used(net):
    net.handler = serve(ollama_routes())
    ollama.version(endpoints={"ollama": {"base_url": "http://192.168.1.5:11434/"}})
    assert str(net.requests[0].url) == "http://192.168.1.5:11434/api/version"


def test_models_route_adds_measured_speeds(client, net, laptop):
    net.handler = serve(ollama_routes())
    store.save_benchmark("ollama:qwen3:8b", 7.0, 50.0, laptop["fingerprint"])
    store.save_benchmark("ollama:qwen3:8b", 99.0, 1.0, "another-machine")
    data = client.get("/api/local/models", headers=AUTH).json()
    assert data["ollama"]["running"] is True
    qwen = next(m for m in data["installed"] if m["name"] == "qwen3:8b")
    assert qwen["benchmark"]["tok_per_sec"] == 7.0
    assert data["loaded"][0]["name"] == "qwen3:8b"


def test_routes_when_ollama_is_off(client, laptop):
    assert client.get("/api/local/status", headers=AUTH).json()["running"] is False
    assert client.get("/api/local/models", headers=AUTH).json() == {
        "ollama": {"running": False, "version": None, "base_url": "http://localhost:11434"},
        "installed": [],
        "loaded": [],
    }
    r = client.delete("/api/local/models/qwen3:8b", headers=AUTH)
    assert r.status_code == 503 and "ollama serve" in r.json()["detail"]


def test_hardware_route(client, laptop):
    data = client.get("/api/local/hardware", headers=AUTH).json()
    assert data["gpu"] is None
    assert data["budgets"] == {"gpu_gb": 0.0, "total_gb": 12.0}


# ─── Pulls ───────────────────────────────────────────────────


def test_throttle():
    now = [0.0]
    throttle = ollama.Throttle(0.25, lambda: now[0])
    assert throttle.ready()
    assert not throttle.ready()
    now[0] = 0.2
    assert not throttle.ready() and throttle.ready(force=True)
    now[0] = 0.5
    assert throttle.ready()


def test_pull_reports_status_changes_and_throttles_the_rest(net):
    net.handler = serve(ollama_routes())
    events: list[dict] = []
    assert ollama.pull("qwen3:8b", events.append, clock=lambda: 0.0) is True
    # The four repeated "pulling a3de…" lines fall inside one throttle window.
    assert [e["status"] for e in events] == [
        "pulling manifest",
        "pulling a3de86cd1c13",
        "pulling ae370d884f10",
        "verifying sha256 digest",
        "writing manifest",
        "success",
    ]
    assert events[-1]["completed"] == events[-1]["total"] == LAYERS_TOTAL
    assert json.loads(net.requests[0].content) == {"model": "qwen3:8b", "stream": True}


def test_pull_reports_every_line_when_time_passes(net):
    net.handler = serve(ollama_routes())
    ticks = iter(range(100))
    events: list[dict] = []
    ollama.pull("qwen3:8b", events.append, clock=lambda: float(next(ticks)))
    assert len(events) == 10
    assert [e["completed"] for e in events[2:6]] == [1_306_344_000, 2_612_688_000, 3_919_032_000, 5_225_376_000]


def test_pull_errors(net):
    net.handler = lambda req: (200, '{"status":"pulling manifest"}\n{"error":"pull model manifest: file does not exist"}\n', NDJSON)
    with pytest.raises(providers.ProviderError, match="file does not exist"):
        ollama.pull("nope:1b", lambda p: None)
    net.handler = lambda req: (500, {"error": "disk full"}, {})
    with pytest.raises(providers.ProviderError, match="disk full"):
        ollama.pull("qwen3:8b", lambda p: None)
    net.handler = lambda req: (200, '{"status":"pulling manifest"}\n', NDJSON)
    with pytest.raises(providers.ProviderError, match="before it finished"):
        ollama.pull("qwen3:8b", lambda p: None)


def test_cancelled_pull_stops_reading(net):
    net.handler = serve(ollama_routes())
    cancel = threading.Event()
    events: list[dict] = []

    def on_progress(p):
        events.append(p)
        cancel.set()

    assert ollama.pull("qwen3:8b", on_progress, cancel=cancel) is False
    assert len(events) == 1


def test_pull_route_runs_in_the_background(client, net, fresh_pulls):
    net.handler = serve(ollama_routes())
    seen = []
    message_bus.subscribe_sync(seen.append)
    try:
        r = client.post("/api/local/pulls", json={"model": "qwen3:8b"}, headers=AUTH)
        assert r.status_code == 202 and r.json()["status"] == "pulling"
        job = wait_for(fresh_pulls, "qwen3:8b")
    finally:
        message_bus.unsubscribe_sync(seen.append)
    assert job["status"] == "success" and job["completed"] == LAYERS_TOTAL
    progress = [m for m in seen if m.message_type == "pull_progress"]
    assert progress and progress[-1].data["status"] == "success"
    assert not any(m.message_type == "pull_progress" for m in message_bus.history)  # live only
    assert client.get("/api/local/pulls", headers=AUTH).json()[0]["status"] == "success"


def test_pull_needs_the_license_accepted_first(client, net, fresh_pulls):
    net.handler = serve(ollama_routes())
    r = client.post("/api/local/pulls", json={"model": "gemma3:4b"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["detail"]["license"]["id"] == "gemma"
    assert not net.requests  # nothing was downloaded
    client.post("/api/local/licenses", json={"license": "gemma"}, headers=AUTH)
    assert client.post("/api/local/pulls", json={"model": "gemma3:4b"}, headers=AUTH).status_code == 202
    wait_for(fresh_pulls, "gemma3:4b")


def test_one_pull_per_model_then_cancel_and_resume(client, net, fresh_pulls):
    release = threading.Event()
    first = fixture_text("ollama_pull.ndjson").splitlines()

    def slow_pull(request):
        release.wait(5)
        return 200, "\n".join(first[:3]) + "\n", NDJSON  # ends early, like a dropped connection

    net.handler = serve(ollama_routes({("POST", "/api/pull"): slow_pull}))
    assert client.post("/api/local/pulls", json={"model": "qwen3:8b"}, headers=AUTH).status_code == 202
    assert client.post("/api/local/pulls", json={"model": "qwen3:8b"}, headers=AUTH).status_code == 409
    assert client.delete("/api/local/pulls/qwen3:8b", headers=AUTH).status_code == 204
    release.set()
    assert wait_for(fresh_pulls, "qwen3:8b")["status"] == "cancelled"
    assert client.delete("/api/local/pulls/qwen3:8b", headers=AUTH).status_code == 404

    net.handler = serve(ollama_routes())  # pulling again resumes in Ollama
    assert client.post("/api/local/pulls", json={"model": "qwen3:8b"}, headers=AUTH).status_code == 202
    assert wait_for(fresh_pulls, "qwen3:8b")["status"] == "success"


def test_a_failed_pull_reports_why(fresh_pulls):
    fresh_pulls.start("qwen3:8b")
    job = wait_for(fresh_pulls, "qwen3:8b")
    assert job["status"] == "error" and "can't reach Ollama" in job["error"]


@pytest.mark.parametrize("model", ["../etc/passwd", "Qwen3:8b", "qwen3:8b;rm -rf", ""])
def test_pull_rejects_bad_names(client, model):
    assert client.post("/api/local/pulls", json={"model": model}, headers=AUTH).status_code == 422


def test_hf_pull_checks_the_repo_license(client, net, fresh_pulls):
    repo = "bartowski/Llama-3.2-1B-Instruct-GGUF"
    net.handler = serve(ollama_routes({("GET", f"/api/models/{repo}"): (200, fixture_json("hf_model_llama.json"), {})}))
    model = f"hf.co/{repo}:Q4_K_M"
    assert client.post("/api/local/pulls", json={"model": model}, headers=AUTH).json()["detail"]["license"]["id"] == "llama3.2"
    client.post("/api/local/licenses", json={"license": "llama3.2"}, headers=AUTH)
    assert client.post("/api/local/pulls", json={"model": model}, headers=AUTH).status_code == 202
    assert wait_for(fresh_pulls, model)["status"] == "success"


# ─── Delete and benchmark ────────────────────────────────────


def test_delete_route(client, net):
    net.handler = serve(ollama_routes({("DELETE", "/api/delete"): (200, "", {})}))
    assert client.delete("/api/local/models/qwen3:8b", headers=AUTH).status_code == 204
    assert json.loads(net.requests[-1].content) == {"model": "qwen3:8b"}
    assert client.delete("/api/local/models/llama3.2:1b", headers=AUTH).status_code == 404
    hf = "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M"
    assert client.delete(f"/api/local/models/{hf}", headers=AUTH).status_code == 204


def test_speeds():
    assert ollama.speeds(fixture_json("ollama_generate.json")) == (pytest.approx(7.0, abs=0.01), pytest.approx(50.0))
    assert ollama.speeds({"eval_count": 0, "eval_duration": 0}) == (None, None)


def test_benchmark_is_stored_per_machine(client, net, laptop):
    net.handler = serve(ollama_routes())
    r = client.post("/api/local/benchmark", json={"model": "qwen3:8b"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["tok_per_sec"] == pytest.approx(7.0, abs=0.01)
    body = json.loads(net.requests[-1].content)
    assert body["stream"] is False and body["options"] == {"num_predict": 128}
    saved = store.get_benchmarks(laptop["fingerprint"])["ollama:qwen3:8b"]
    assert saved["prefill_tok_per_sec"] == pytest.approx(50.0) and saved["measured_at"]


def test_benchmark_of_a_missing_model(client, net, laptop):
    net.handler = serve(ollama_routes({("POST", "/api/generate"): (404, {"error": "model 'nope' not found"}, {})}))
    r = client.post("/api/local/benchmark", json={"model": "nope"}, headers=AUTH)
    assert r.status_code == 502 and "not found" in r.json()["detail"]


def test_key_check_for_ollama_uses_the_version(net):
    net.handler = serve(ollama_routes())
    assert providers.check("ollama")["detail"] == "Ollama 0.20.0"
    assert providers.check("ollama", {"ollama": {"base_url": "http://localhost:9"}})["status"] == "ok"
    net.handler = None
    assert providers.check("ollama")["status"] == "unreachable"
    config.load_settings()  # settings untouched by checks
