"""
Model providers: streaming chat, usage and cost, Privacy Mode, key problems.

A model ref is "provider:model", split on the first colon, e.g.
"ollama:qwen3:8b" or "anthropic:claude-sonnet-5-5". Three wire formats cover
every provider: OpenAI-compatible (OpenAI, Gemini, OpenRouter, Groq, DeepSeek,
Mistral, xAI, custom endpoints), Anthropic, and Ollama's native API.

Keys come only from juli.keystore and are never logged: messages show the
provider name and the key's last 4 characters at most.
"""

import ipaddress
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anthropic
import httpx
import openai

from juli import keystore

log = logging.getLogger(__name__)

_PRESETS = json.loads((Path(__file__).with_name("providers.json")).read_text(encoding="utf-8"))
PROVIDERS: dict[str, dict] = _PRESETS["providers"]
MODELS: dict[str, dict] = _PRESETS["models"]

TIMEOUT = httpx.Timeout(600.0, connect=10.0)
CHECK_TIMEOUT = 15.0
MAX_BACKOFF_SECONDS = 60.0
# Anthropic requires max_tokens. Used for models without a known maximum.
DEFAULT_ANTHROPIC_MAX_OUTPUT = 8192
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"

# Test seams: tests swap in mock transports. None means the real network.
SDK_HTTP_CLIENT: Callable[[], Any] | None = None  # builds the http client for the openai/anthropic SDKs
HTTP_TRANSPORT: httpx.BaseTransport | None = None  # for direct httpx calls (Ollama, OpenRouter)

# Key problems that pause a run for a decision; the others are retried.
PAUSING = ("missing", "invalid", "out_of_credit")


class PrivacyViolation(RuntimeError):
    """A cloud model was called while Privacy Mode is on."""


@dataclass
class KeyProblem:
    kind: str  # missing, invalid, out_of_credit, rate_limit, overloaded
    message: str
    retry_after: float | None = None


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str, problem: KeyProblem | None = None) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.problem = problem


@dataclass
class Usage:
    tokens_in: int
    tokens_out: int
    cost_usd: float | None  # None when the model has no known price
    warnings: list[str] = field(default_factory=list)


# ─── Presets, refs, privacy, cost ────────────────────────────


def split_ref(ref: str) -> tuple[str, str]:
    provider, sep, model = ref.partition(":")
    if not (sep and provider and model):
        raise ValueError(f"Model '{ref}' isn't a provider:model ref")
    return provider, model


def provider_info(provider: str, endpoints: Mapping[str, dict] | None = None) -> dict | None:
    """A provider's preset, merged with any custom endpoint of the same id."""
    custom = (endpoints or {}).get(provider)
    preset = PROVIDERS.get(provider)
    if custom is None:
        return preset
    return {"label": provider, "kind": "openai", **(preset or {}), **custom}


def is_local_url(url: str) -> bool:
    """True for localhost, loopback and private LAN addresses. Names aren't resolved."""
    host = (urlparse(url).hostname or "").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def is_local(ref: str, endpoints: Mapping[str, dict] | None = None) -> bool:
    try:
        info = provider_info(split_ref(ref)[0], endpoints)
    except ValueError:
        return False
    return bool(info) and is_local_url(info["base_url"])


def cost(ref: str, tokens_in: int, tokens_out: int, endpoints: Mapping[str, dict] | None = None) -> float | None:
    """Cost in USD. Local models are free; unknown cloud prices are None."""
    if is_local(ref, endpoints):
        return 0.0
    price = MODELS.get(ref)
    if not price:
        return None
    rate_in, rate_out = price["in"], price["out"]
    tier = price.get("long_context")
    if tier and tokens_in > tier["above"]:
        rate_in, rate_out = tier["in"], tier["out"]
    return (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000


def preset_refs() -> list[str]:
    return list(MODELS)


# ─── Errors and headers (pure) ───────────────────────────────

_PROBLEM_TEXT = {
    "missing": "no API key is set",
    "invalid": "the API key was rejected",
    "out_of_credit": "the account is out of credit",
    "rate_limit": "rate limited",
    "overloaded": "the provider is overloaded",
}


def _as_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, (bytes, bytearray)):
        return body.decode("utf-8", "replace")
    return body if isinstance(body, str) else json.dumps(body)


def retry_after(headers: Mapping[str, str] | None) -> float | None:
    """Retry-After in seconds (number or HTTP date), or None."""
    value = {k.lower(): v for k, v in (headers or {}).items()}.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def classify_error(kind: str, status: int, body: Any, headers: Mapping[str, str] | None) -> KeyProblem | None:
    """What an error response means for the key, or None if it isn't a key problem.

    kind is the error format: "openai" (every OpenAI-compatible provider),
    "anthropic" or "gemini".
    """
    text = _as_text(body).lower()
    wait = retry_after(headers)

    def problem(name: str) -> KeyProblem:
        return KeyProblem(name, _PROBLEM_TEXT[name], wait if name in ("rate_limit", "overloaded") else None)

    if kind == "anthropic":
        if "credit balance is too low" in text:
            return problem("out_of_credit")
        if status in (401, 403):
            return problem("invalid")
        if status == 429:
            return problem("rate_limit")
        if status == 529:
            return problem("overloaded")
        return None
    if kind == "gemini":
        if status == 429:
            exhausted = "resource_exhausted" in text and "exceeded your current quota" in text
            return problem("out_of_credit" if exhausted else "rate_limit")
        if status in (401, 403) or "api key not valid" in text:
            return problem("invalid")
        return None
    # OpenAI and the other OpenAI-compatible APIs. 402 is how OpenRouter and
    # DeepSeek report an empty balance.
    if status == 401:
        return problem("invalid")
    if status == 402:
        return problem("out_of_credit")
    if status == 429:
        return problem("out_of_credit" if "insufficient_quota" in text else "rate_limit")
    return None


_REMAINING = [
    (re.compile(r"x-ratelimit-remaining-(.+)"), "x-ratelimit-limit-{}"),
    (re.compile(r"anthropic-ratelimit-(.+)-remaining"), "anthropic-ratelimit-{}-limit"),
]


def low_quota_warnings(headers: Mapping[str, str] | None, threshold: float = 0.10) -> list[str]:
    """Warnings for each rate-limit window with less than 10% left."""
    lowered = {k.lower(): v for k, v in (headers or {}).items()}
    warnings = []
    for name, value in lowered.items():
        for pattern, limit_name in _REMAINING:
            match = pattern.fullmatch(name)
            if not match:
                continue
            try:
                remaining, limit = int(value), int(lowered[limit_name.format(match[1])])
            except (KeyError, ValueError):
                continue
            if limit > 0 and remaining < limit * threshold:
                warnings.append(f"{match[1]}: {remaining} of {limit} left in this window")
    return warnings


_KEYLIKE = re.compile(r"(?:sk-|sk_|gsk_|xai-|AIza)[A-Za-z0-9_\-\*]{6,}")


def redact(text: str, key: str | None = None) -> str:
    """Hide keys in a message, keeping only their last 4 characters."""
    if key:
        text = text.replace(key, keystore.key_hint(key) or "••••")
    return _KEYLIKE.sub(lambda m: "••••" + m.group(0)[-4:], text)


def _error_message(body: Any) -> str:
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict):
            return str(inner.get("message") or inner)
        return str(inner)
    return _as_text(body)[:500]


def _status_error(provider: str, kind: str, status: int, body: Any, headers: Any, key: str | None) -> ProviderError:
    problem = classify_error(kind, status, body, headers)
    detail = redact(_error_message(body) or f"HTTP {status}", key)
    if problem:
        problem.message = f"{problem.message} ({detail})"
        return ProviderError(provider, problem.message, problem)
    return ProviderError(provider, f"HTTP {status}: {detail}")


# ─── Streaming ───────────────────────────────────────────────


def _sdk_http_client() -> Any:
    return SDK_HTTP_CLIENT() if SDK_HTTP_CLIENT else None


def http_client() -> httpx.Client:
    """An httpx client through the HTTP_TRANSPORT test seam. Use it for every direct HTTP call."""
    return httpx.Client(timeout=TIMEOUT, transport=HTTP_TRANSPORT)


def _resolve(ref: str, privacy: bool, endpoints: Mapping[str, dict] | None) -> tuple[str, str, dict, str | None]:
    provider, model = split_ref(ref)
    info = provider_info(provider, endpoints)
    if info is None:
        raise ProviderError(provider, f"unknown provider '{provider}'")
    local = is_local_url(info["base_url"])
    if privacy and not local:
        raise PrivacyViolation(f"Privacy Mode is on: {ref} is a cloud model")
    key = keystore.get_key(provider) if info.get("key", True) else None
    if info.get("key", True) and not key and not local:
        raise ProviderError(provider, _PROBLEM_TEXT["missing"], KeyProblem("missing", _PROBLEM_TEXT["missing"]))
    return provider, model, info, key


def stream(
    ref: str,
    messages: list[dict],
    *,
    privacy: bool = False,
    max_tokens: int | None = None,
    num_ctx: int | None = None,
    cancel: threading.Event | None = None,
    endpoints: Mapping[str, dict] | None = None,
) -> Iterator[str | Usage]:
    """Stream a chat reply: text deltas, then one Usage.

    Rate limits and overload are retried, honouring Retry-After, for at most
    about a minute in total and only before any text has arrived. Setting
    `cancel` ends the stream early (no Usage is yielded then).
    """
    provider, model, info, key = _resolve(ref, privacy, endpoints)
    kind = info["kind"]
    waited, attempt = 0.0, 0
    while True:
        started = False
        try:
            if kind == "anthropic":
                chunks = _anthropic(provider, model, info, key, messages, max_tokens or _max_output(ref))
            elif kind == "ollama":
                chunks = _ollama(provider, model, info, messages, max_tokens, num_ctx)
            else:
                chunks = _openai(provider, model, info, key, messages, max_tokens)
            for item in chunks:
                if cancel is not None and cancel.is_set():
                    chunks.close()  # closes the SDK or HTTP stream
                    return
                if isinstance(item, Usage):
                    item.cost_usd = cost(ref, item.tokens_in, item.tokens_out, endpoints)
                else:
                    started = True
                yield item
            return
        except ProviderError as e:
            problem = e.problem
            if started or not problem or problem.kind not in ("rate_limit", "overloaded"):
                raise
            delay = problem.retry_after if problem.retry_after is not None else min(2.0**attempt, 20.0)
            if waited + delay > MAX_BACKOFF_SECONDS:
                raise
            log.info("%s %s; retrying in %.0fs", provider, problem.kind, delay)
            if cancel is not None:
                if cancel.wait(delay):
                    return
            else:
                time.sleep(delay)
            waited += delay
            attempt += 1


def _max_output(ref: str) -> int:
    return int(MODELS.get(ref, {}).get("max_output", DEFAULT_ANTHROPIC_MAX_OUTPUT))


def _openai(provider, model, info, key, messages, max_tokens) -> Iterator[str | Usage]:
    kwargs: dict[str, Any] = {}
    if max_tokens:
        # OpenAI's own API wants max_completion_tokens; compatible APIs take max_tokens.
        kwargs["max_completion_tokens" if provider == "openai" else "max_tokens"] = max_tokens
    client = openai.OpenAI(
        api_key=key or "not-needed",
        base_url=info["base_url"],
        max_retries=0,
        timeout=TIMEOUT.read,
        http_client=_sdk_http_client(),
    )
    with client:
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs,
            )
            tokens_in = tokens_out = 0
            with raw.parse() as chunks:
                for chunk in chunks:
                    if chunk.usage:
                        tokens_in, tokens_out = chunk.usage.prompt_tokens, chunk.usage.completion_tokens
                    for choice in chunk.choices:
                        if choice.delta and choice.delta.content:
                            yield choice.delta.content
        except openai.APIStatusError as e:
            raise _status_error(provider, info.get("errors", "openai"), e.status_code, e.body, e.response.headers, key) from None
        except openai.APIConnectionError as e:
            raise ProviderError(provider, f"can't reach {info['base_url']} ({type(e).__name__})") from None
        except openai.APIError as e:
            raise ProviderError(provider, redact(str(e), key)) from None
    yield Usage(tokens_in, tokens_out, None, low_quota_warnings(raw.headers))


def _anthropic(provider, model, info, key, messages, max_tokens) -> Iterator[str | Usage]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [m for m in messages if m["role"] != "system"]
    client = anthropic.Anthropic(
        api_key=key,
        base_url=info["base_url"],
        max_retries=0,
        timeout=TIMEOUT.read,
        http_client=_sdk_http_client(),
    )
    with client:
        try:
            extra = {"system": system} if system else {}
            with client.messages.stream(model=model, max_tokens=max_tokens, messages=turns, **extra) as s:
                headers = s.response.headers
                yield from s.text_stream
                usage = s.get_final_message().usage
        except anthropic.APIStatusError as e:
            raise _status_error(provider, "anthropic", e.status_code, e.body, e.response.headers, key) from None
        except anthropic.APIConnectionError as e:
            raise ProviderError(provider, f"can't reach {info['base_url']} ({type(e).__name__})") from None
        except anthropic.APIError as e:
            raise ProviderError(provider, redact(str(e), key)) from None
    tokens_in = usage.input_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0)
    yield Usage(tokens_in, usage.output_tokens, None, low_quota_warnings(headers))


def _ollama(provider, model, info, messages, max_tokens, num_ctx) -> Iterator[str | Usage]:
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    options = {k: v for k, v in (("num_ctx", num_ctx), ("num_predict", max_tokens)) if v}
    if options:
        body["options"] = options
    url = info["base_url"].rstrip("/") + "/api/chat"
    tokens_in = tokens_out = 0
    try:
        with http_client() as http, http.stream("POST", url, json=body) as response:
            if response.status_code >= 400:
                response.read()
                raise ProviderError(provider, f"HTTP {response.status_code}: {_error_message(_json_or_text(response))}")
            for line in response.iter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise ProviderError(provider, str(data["error"]))
                text = (data.get("message") or {}).get("content")
                if text:
                    yield text
                if data.get("done"):
                    tokens_in, tokens_out = data.get("prompt_eval_count", 0), data.get("eval_count", 0)
    except httpx.HTTPError as e:
        raise ProviderError(provider, f"can't reach Ollama at {info['base_url']} ({type(e).__name__})") from None
    yield Usage(tokens_in, tokens_out, None)


def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


# ─── Key health check ────────────────────────────────────────


def check(provider: str, endpoints: Mapping[str, dict] | None = None, privacy: bool = False) -> dict:
    """A cheap call that gives a provider's key a health badge.

    status: ok, missing, invalid, out_of_credit, rate_limit, overloaded,
    unreachable, error, skipped (Privacy Mode) or unknown_provider. For
    OpenAI-compatible providers, "models" lists the endpoint's model ids.
    """
    result: dict[str, Any] = {"provider": provider, "status": "ok", "detail": ""}
    info = provider_info(provider, endpoints)
    if info is None:
        return {**result, "status": "unknown_provider", "detail": f"Unknown provider '{provider}'"}
    local = is_local_url(info["base_url"])
    if privacy and not local:
        return {**result, "status": "skipped", "detail": "Privacy Mode is on, so cloud keys aren't contacted"}
    key = keystore.get_key(provider) if info.get("key", True) else None
    if info.get("key", True) and not key and not local:
        return {**result, "status": "missing", "detail": _PROBLEM_TEXT["missing"]}

    try:
        if info["kind"] == "ollama":
            from juli.local import ollama  # it imports this module

            result["detail"] = f"Ollama {ollama.version(info['base_url'])}".strip()
        elif provider == "openrouter":
            with http_client() as http:
                r = http.get(OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {key}"}, timeout=CHECK_TIMEOUT)
            if r.status_code >= 400:
                raise _status_error(provider, "openai", r.status_code, _json_or_text(r), r.headers, key)
            data = r.json().get("data", {})
            result["balance"] = {k: data.get(k) for k in ("limit", "usage", "limit_remaining")}
        elif info["kind"] == "anthropic":
            client = anthropic.Anthropic(
                api_key=key, base_url=info["base_url"], max_retries=0, timeout=CHECK_TIMEOUT, http_client=_sdk_http_client()
            )
            with client:
                client.models.list(limit=1)
        else:
            client = openai.OpenAI(
                api_key=key or "not-needed",
                base_url=info["base_url"],
                max_retries=0,
                timeout=CHECK_TIMEOUT,
                http_client=_sdk_http_client(),
            )
            with client:
                result["models"] = sorted(m.id for m in client.models.list())
    except (openai.APIStatusError, anthropic.APIStatusError) as e:
        kind = "anthropic" if info["kind"] == "anthropic" else info.get("errors", "openai")
        err = _status_error(provider, kind, e.status_code, e.body, e.response.headers, key)
        return _failed(result, err)
    except ProviderError as err:
        return _failed(result, err)
    except (openai.APIConnectionError, anthropic.APIConnectionError, httpx.HTTPError) as e:
        return {**result, "status": "unreachable", "detail": f"Can't reach {info['base_url']} ({type(e).__name__})"}
    except ValueError:  # a 200 whose body isn't the JSON we expect
        return {**result, "status": "error", "detail": f"Unexpected response from {info['base_url']}"}
    return result


def _failed(result: dict, err: ProviderError) -> dict:
    status = err.problem.kind if err.problem else "error"
    log.warning("Key check failed for %s: %s", err.provider, status)
    return {**result, "status": status, "detail": str(err)}
