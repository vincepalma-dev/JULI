import json
import logging
import threading
from pathlib import Path

import pytest

from juli import keystore, providers
from juli.providers import KeyProblem, PrivacyViolation, ProviderError, Usage

from .conftest import AUTH

FIXTURES = Path(__file__).parent / "fixtures"
SSE = {"content-type": "text/event-stream"}
MESSAGES = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def collect(ref, **kwargs):
    items = list(providers.stream(ref, MESSAGES, **kwargs))
    text = "".join(i for i in items if isinstance(i, str))
    usage = [i for i in items if isinstance(i, Usage)]
    assert len(usage) == 1
    return text, usage[0]


# ─── classify_error: the guardrail table ─────────────────────


@pytest.mark.parametrize(
    "kind, status, body, expected",
    [
        ("openai", 401, {"message": "Incorrect API key provided", "code": "invalid_api_key"}, "invalid"),
        ("openai", 429, {"message": "You exceeded your current quota", "code": "insufficient_quota"}, "out_of_credit"),
        ("openai", 429, {"message": "Rate limit reached for requests", "code": "rate_limit_exceeded"}, "rate_limit"),
        ("openai", 402, {"message": "Insufficient credits"}, "out_of_credit"),
        ("openai", 400, {"message": "bad request"}, None),
        ("openai", 500, {"message": "server error"}, None),
        ("anthropic", 401, {"type": "error", "error": {"type": "authentication_error"}}, "invalid"),
        ("anthropic", 403, {"type": "error", "error": {"type": "permission_error"}}, "invalid"),
        (
            "anthropic",
            400,
            {"error": {"message": "Your credit balance is too low to access the Anthropic API."}},
            "out_of_credit",
        ),
        ("anthropic", 429, {"error": {"type": "rate_limit_error"}}, "rate_limit"),
        ("anthropic", 529, {"error": {"type": "overloaded_error"}}, "overloaded"),
        ("anthropic", 400, {"error": {"type": "invalid_request_error"}}, None),
        (
            "gemini",
            429,
            [{"error": {"code": 429, "message": "You exceeded your current quota.", "status": "RESOURCE_EXHAUSTED"}}],
            "out_of_credit",
        ),
        ("gemini", 429, [{"error": {"code": 429, "message": "Too many requests", "status": "RESOURCE_EXHAUSTED"}}], "rate_limit"),
        ("gemini", 400, [{"error": {"message": "API key not valid. Please pass a valid API key."}}], "invalid"),
        ("gemini", 500, {"error": {"message": "internal"}}, None),
    ],
)
def test_classify_error(kind, status, body, expected):
    problem = providers.classify_error(kind, status, body, {})
    assert (problem.kind if problem else None) == expected


def test_rate_limit_carries_retry_after():
    problem = providers.classify_error("anthropic", 429, {}, {"Retry-After": "12"})
    assert problem == KeyProblem("rate_limit", "rate limited", 12.0)
    assert providers.classify_error("openai", 401, {}, {"retry-after": "5"}).retry_after is None


def test_retry_after_parses_numbers_and_dates():
    assert providers.retry_after({"retry-after": "3"}) == 3.0
    assert providers.retry_after({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}) == 0.0  # in the past
    assert providers.retry_after({"retry-after": "soon"}) is None
    assert providers.retry_after(None) is None


def test_low_quota_warnings_below_ten_percent():
    headers = {
        "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-requests": "50",
        "x-ratelimit-limit-tokens": "100000",
        "x-ratelimit-remaining-tokens": "90000",
        "anthropic-ratelimit-output-tokens-limit": "8000",
        "anthropic-ratelimit-output-tokens-remaining": "100",
        "anthropic-ratelimit-requests-limit": "50",
        "anthropic-ratelimit-requests-remaining": "not-a-number",
    }
    assert providers.low_quota_warnings(headers) == [
        "requests: 50 of 1000 left in this window",
        "output-tokens: 100 of 8000 left in this window",
    ]
    assert providers.low_quota_warnings({}) == []


def test_redact_keeps_only_last_four():
    key = "sk-test-not-a-real-key-1234"
    text = providers.redact(f"Incorrect API key provided: {key}. Also AIzaSyA1234567890abcdWXYZ.", key)
    assert key not in text and "AIzaSyA1234567890abcd" not in text
    assert "••••1234" in text and "••••WXYZ" in text
    # A partly masked key echoed by a provider is hidden too.
    assert "abcdefgh" not in providers.redact("key sk-proj-abcdefgh*****1234 rejected")


# ─── Refs, privacy, cost ─────────────────────────────────────


def test_split_ref_keeps_ollama_tags():
    assert providers.split_ref("ollama:qwen3:8b") == ("ollama", "qwen3:8b")
    with pytest.raises(ValueError):
        providers.split_ref("gpt4")


@pytest.mark.parametrize(
    "url, local",
    [
        ("http://localhost:11434", True),
        ("http://127.0.0.1:1234/v1", True),
        ("http://[::1]:8080", True),
        ("http://192.168.1.20:11434", True),
        ("http://10.0.0.5", True),
        ("http://172.16.4.4", True),
        ("http://lab.localhost", True),
        ("https://api.openai.com/v1", False),
        ("http://8.8.8.8", False),
        ("http://my-gpu-box", False),  # names aren't resolved, so they count as cloud
    ],
)
def test_is_local_url(url, local):
    assert providers.is_local_url(url) is local


def test_custom_endpoint_merges_over_presets():
    endpoints = {"lmstudio": {"base_url": "http://localhost:1234/v1"}, "ollama": {"base_url": "http://192.168.1.9:11434"}}
    assert providers.provider_info("lmstudio", endpoints)["kind"] == "openai"
    assert providers.provider_info("ollama", endpoints) == {
        "label": "Ollama",
        "kind": "ollama",
        "base_url": "http://192.168.1.9:11434",
        "key": False,
    }
    assert providers.is_local("lmstudio:any-model", endpoints)


def test_cost():
    assert providers.cost("openai:gpt-6.1-sol", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert providers.cost("ollama:qwen3:8b", 10**9, 10**9) == 0.0
    assert providers.cost("openai:gpt-unknown", 100, 100) is None
    # Haiku 5.5 is cheaper up to 100k prompt tokens.
    assert providers.cost("anthropic:claude-haiku-5-5", 100_000, 0) == pytest.approx(0.01)
    assert providers.cost("anthropic:claude-haiku-5-5", 100_001, 0) == pytest.approx(0.0500005)


def test_privacy_blocks_cloud_before_any_request(net):
    keystore.set_key("openai", "sk-test-00001111")
    with pytest.raises(PrivacyViolation):
        list(providers.stream("openai:gpt-6.1-sol", MESSAGES, privacy=True))
    assert net.requests == []


def test_missing_key_is_a_key_problem_without_a_request(net):
    with pytest.raises(ProviderError) as e:
        list(providers.stream("anthropic:claude-sonnet-5-5", MESSAGES))
    assert e.value.problem.kind == "missing"
    assert net.requests == []


# ─── OpenAI-compatible ───────────────────────────────────────


def test_openai_stream_from_recorded_fixture(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    net.handler = lambda req: (200, fixture("openai_stream.sse"), {**SSE, "x-ratelimit-limit-requests": "100", "x-ratelimit-remaining-requests": "5"})

    text, usage = collect("openai:gpt-6.1-sol", max_tokens=256)

    assert text == "Hello world"
    assert (usage.tokens_in, usage.tokens_out) == (1000, 500)
    assert usage.cost_usd == pytest.approx(0.007)
    assert usage.warnings == ["requests: 5 of 100 left in this window"]
    (req,) = net.requests
    body = json.loads(req.content)
    assert body["stream_options"] == {"include_usage": True}
    assert body["max_completion_tokens"] == 256 and "max_tokens" not in body
    assert req.headers["authorization"] == "Bearer sk-test-aaaabbbb"
    assert str(req.url) == "https://api.openai.com/v1/chat/completions"


def test_compatible_providers_get_max_tokens_and_their_base_url(net):
    keystore.set_key("google", "AIza-test-key-0000")
    net.handler = lambda req: (200, fixture("openai_stream.sse"), SSE)
    collect("google:gemini-3.8-flash", max_tokens=99)
    (req,) = net.requests
    assert json.loads(req.content)["max_tokens"] == 99
    assert str(req.url).startswith("https://generativelanguage.googleapis.com/v1beta/openai/")


def test_openai_no_max_tokens_when_unset(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    net.handler = lambda req: (200, fixture("openai_stream.sse"), SSE)
    collect("openai:gpt-6.1-sol")
    body = json.loads(net.requests[0].content)
    assert "max_tokens" not in body and "max_completion_tokens" not in body


def test_openai_out_of_credit_is_not_retried(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    net.handler = lambda req: (429, {"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}, {})
    with pytest.raises(ProviderError) as e:
        list(providers.stream("openai:gpt-6.1-sol", MESSAGES))
    assert e.value.problem.kind == "out_of_credit"
    assert len(net.requests) == 1


def test_invalid_key_error_never_shows_the_key(net, caplog):
    key = "sk-test-secret-value-9876"
    keystore.set_key("openai", key)
    net.handler = lambda req: (401, {"error": {"message": f"Incorrect API key provided: {key}"}}, {})
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError) as e:
        list(providers.stream("openai:gpt-6.1-sol", MESSAGES))
    assert e.value.problem.kind == "invalid"
    assert key not in str(e.value) and "••••9876" in str(e.value)
    assert key not in caplog.text


def test_rate_limit_backs_off_honouring_retry_after(net, monkeypatch):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    sleeps = []
    monkeypatch.setattr(providers.time, "sleep", sleeps.append)
    responses = iter([(429, {"error": {"message": "slow down"}}, {"retry-after": "7"}), (200, fixture("openai_stream.sse"), SSE)])
    net.handler = lambda req: next(responses)

    text, _ = collect("openai:gpt-6.1-sol")

    assert text == "Hello world"
    assert sleeps == [7.0]


def test_rate_limit_gives_up_after_about_a_minute(net, monkeypatch):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    sleeps = []
    monkeypatch.setattr(providers.time, "sleep", sleeps.append)
    net.handler = lambda req: (429, {"error": {"message": "slow down"}}, {"retry-after": "25"})
    with pytest.raises(ProviderError) as e:
        list(providers.stream("openai:gpt-6.1-sol", MESSAGES))
    assert e.value.problem.kind == "rate_limit"
    assert sleeps == [25.0, 25.0]  # a third wait would pass 60 s


def test_cancel_during_backoff_ends_the_stream(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    net.handler = lambda req: (429, {"error": {"message": "slow down"}}, {"retry-after": "30"})
    cancel = threading.Event()
    cancel.set()
    assert list(providers.stream("openai:gpt-6.1-sol", MESSAGES, cancel=cancel)) == []


# ─── Anthropic ───────────────────────────────────────────────


def test_anthropic_stream_from_recorded_fixture(net):
    keystore.set_key("anthropic", "sk-ant-test-ccccdddd")
    headers = {**SSE, "anthropic-ratelimit-tokens-limit": "1000", "anthropic-ratelimit-tokens-remaining": "10"}
    net.handler = lambda req: (200, fixture("anthropic_stream.sse"), headers)

    text, usage = collect("anthropic:claude-sonnet-5-5")

    assert text == "Hi there"
    assert (usage.tokens_in, usage.tokens_out) == (2000, 300)
    assert usage.cost_usd == pytest.approx(0.007)
    assert usage.warnings == ["tokens: 10 of 1000 left in this window"]
    body = json.loads(net.requests[0].content)
    assert body["system"] == "Be brief."
    assert body["messages"] == [{"role": "user", "content": "Hi"}]
    assert body["max_tokens"] == 128000  # Anthropic requires it: the model's maximum when unset
    assert "temperature" not in body


def test_anthropic_role_limit_is_passed(net):
    keystore.set_key("anthropic", "sk-ant-test-ccccdddd")
    net.handler = lambda req: (200, fixture("anthropic_stream.sse"), SSE)
    collect("anthropic:claude-sonnet-5-5", max_tokens=1024)
    assert json.loads(net.requests[0].content)["max_tokens"] == 1024


def test_anthropic_low_credit(net):
    keystore.set_key("anthropic", "sk-ant-test-ccccdddd")
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}}
    net.handler = lambda req: (400, body, {})
    with pytest.raises(ProviderError) as e:
        list(providers.stream("anthropic:claude-sonnet-5-5", MESSAGES))
    assert e.value.problem.kind == "out_of_credit"


def test_anthropic_overloaded_is_retried(net, monkeypatch):
    keystore.set_key("anthropic", "sk-ant-test-ccccdddd")
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    overloaded = (529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}, {})
    responses = iter([overloaded, (200, fixture("anthropic_stream.sse"), SSE)])
    net.handler = lambda req: next(responses)
    assert collect("anthropic:claude-sonnet-5-5")[0] == "Hi there"


# ─── Ollama ──────────────────────────────────────────────────


def test_ollama_stream_from_recorded_fixture(net):
    net.handler = lambda req: (200, fixture("ollama_chat.ndjson"), {"content-type": "application/x-ndjson"})

    text, usage = collect("ollama:qwen3:8b", privacy=True, max_tokens=64, num_ctx=8192)

    assert text == "Local reply"
    assert (usage.tokens_in, usage.tokens_out, usage.cost_usd) == (42, 7, 0.0)
    (req,) = net.requests
    assert str(req.url) == "http://localhost:11434/api/chat"
    body = json.loads(req.content)
    assert body["model"] == "qwen3:8b" and body["stream"] is True
    assert body["options"] == {"num_ctx": 8192, "num_predict": 64}


def test_ollama_error(net):
    net.handler = lambda req: (404, {"error": "model 'nope' not found"}, {})
    with pytest.raises(ProviderError, match="not found") as e:
        list(providers.stream("ollama:nope", MESSAGES))
    assert e.value.problem is None


def test_ollama_unreachable(net):
    with pytest.raises(ProviderError, match="can't reach Ollama"):
        list(providers.stream("ollama:qwen3:8b", MESSAGES))


# ─── Key health checks ───────────────────────────────────────


def test_check_ok_lists_models(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    net.handler = lambda req: (200, {"object": "list", "data": [{"id": "gpt-6.1-sol", "object": "model", "created": 1, "owned_by": "openai"}]}, {})
    assert providers.check("openai")["status"] == "ok"
    assert net.requests[0].url.path == "/v1/models"


def test_check_invalid_key_logs_no_key(net, caplog):
    key = "sk-ant-test-wrong-key-4321"
    keystore.set_key("anthropic", key)
    net.handler = lambda req: (401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}, {})
    caplog.set_level(logging.DEBUG)
    result = providers.check("anthropic")
    assert result["status"] == "invalid"
    assert key not in json.dumps(result) and key not in caplog.text


def test_check_openrouter_reports_balance(net):
    keystore.set_key("openrouter", "sk-or-test-eeeeffff")
    net.handler = lambda req: (200, {"data": {"label": "k", "limit": 20, "usage": 5.5, "limit_remaining": 14.5}}, {})
    result = providers.check("openrouter")
    assert result["status"] == "ok"
    assert result["balance"] == {"limit": 20, "usage": 5.5, "limit_remaining": 14.5}
    assert str(net.requests[0].url) == providers.OPENROUTER_KEY_URL


def test_check_ollama_version(net):
    net.handler = lambda req: (200, {"version": "0.12.3"}, {})
    assert providers.check("ollama") == {"provider": "ollama", "status": "ok", "detail": "Ollama 0.12.3"}


def test_check_statuses_without_network(net):
    assert providers.check("openai")["status"] == "missing"
    keystore.set_key("openai", "sk-test-aaaabbbb")
    assert providers.check("openai")["status"] == "unreachable"
    assert providers.check("openai", privacy=True)["status"] == "skipped"
    assert providers.check("nosuch")["status"] == "unknown_provider"


def test_saving_a_key_checks_it(client, net):
    net.handler = lambda req: (401, {"error": {"message": "Incorrect API key provided"}}, {})
    r = client.put("/api/settings/keys", json={"openai": "sk-bad-key-000011112222"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["health"]["openai"]["status"] == "invalid"
    assert "sk-bad-key-0000" not in r.text


def test_provider_routes(client, net):
    listed = {p["id"]: p for p in client.get("/api/providers", headers=AUTH).json()}
    assert listed["ollama"]["local"] and not listed["ollama"]["needs_key"]
    assert {m["ref"] for m in listed["anthropic"]["models"]} >= {"anthropic:claude-opus-5-5"}
    net.handler = lambda req: (200, {"version": "0.12.3"}, {})
    assert client.post("/api/providers/ollama/check", headers=AUTH).json()["status"] == "ok"
    assert client.post("/api/providers/Bad-Id/check", headers=AUTH).status_code == 422


def test_cancel_after_the_first_chunk_ends_the_stream(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    net.handler = lambda req: (200, fixture("openai_stream.sse"), SSE)
    cancel = threading.Event()
    chunks = providers.stream("openai:gpt-6.1-sol", MESSAGES, cancel=cancel)
    assert next(chunks) == "Hello"
    cancel.set()
    assert list(chunks) == []  # no more text and no Usage


def test_check_reports_a_response_that_is_not_json(net):
    net.handler = lambda req: (200, "<html>not ollama</html>", {"content-type": "text/html"})
    result = providers.check("ollama")
    assert result["status"] == "error"
    assert "Unexpected response from http://localhost:11434" in result["detail"]
