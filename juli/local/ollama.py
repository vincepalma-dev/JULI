"""
Ollama model management: version, installed and loaded models, pulls,
deletes and benchmarks. Chat streaming lives in juli.providers.

Every request goes through providers.http_client(), so tests serve recorded
responses. Functions raise httpx.HTTPError when Ollama can't be reached and
ProviderError when it answers with an error.

A pull streams NDJSON progress, reported at most about 4 times a second.
Pulls are resumable: Ollama keeps what it has downloaded, so pulling the same
model again after a cancel or a failure continues where it stopped.
"""

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping

import httpx

from juli import providers, store
from juli.bus import AgentMessage, MessageBus, message_bus
from juli.local import hardware

log = logging.getLogger(__name__)

PULL_INTERVAL = 0.25  # seconds between progress events
BENCH_PROMPT = "Explain in one paragraph how a hash map works."
BENCH_TOKENS = 128


def base_url(endpoints: Mapping[str, dict] | None = None) -> str:
    info = providers.provider_info("ollama", endpoints) or providers.PROVIDERS["ollama"]
    return info["base_url"].rstrip("/")


def _failure(r: httpx.Response) -> providers.ProviderError:
    try:
        body = r.json()
    except ValueError:
        body = None
    detail = body.get("error") if isinstance(body, dict) else None
    return providers.ProviderError("ollama", f"HTTP {r.status_code}: {detail or r.reason_phrase}")


def _request(
    method: str,
    path: str,
    endpoints: Mapping[str, dict] | None = None,
    *,
    base: str | None = None,
    timeout: float | httpx.Timeout = providers.CHECK_TIMEOUT,
    **kwargs,
) -> httpx.Response:
    with providers.http_client() as http:
        r = http.request(method, (base or base_url(endpoints)).rstrip("/") + path, timeout=timeout, **kwargs)
    if r.status_code >= 400:
        raise _failure(r)
    return r


def version(base: str | None = None, endpoints: Mapping[str, dict] | None = None) -> str:
    return str(_request("GET", "/api/version", endpoints, base=base).json().get("version", ""))


def tags(endpoints: Mapping[str, dict] | None = None) -> list[dict]:
    """Installed models."""
    return _request("GET", "/api/tags", endpoints).json().get("models") or []


def ps(endpoints: Mapping[str, dict] | None = None) -> list[dict]:
    """Models loaded in memory right now."""
    return _request("GET", "/api/ps", endpoints).json().get("models") or []


def status(endpoints: Mapping[str, dict] | None = None) -> dict:
    try:
        return {"running": True, "version": version(endpoints=endpoints), "base_url": base_url(endpoints)}
    except (httpx.HTTPError, providers.ProviderError, ValueError):
        return {"running": False, "version": None, "base_url": base_url(endpoints)}


def installed(endpoints: Mapping[str, dict] | None = None) -> set[str]:
    """Names of the installed models; empty when Ollama isn't running."""
    try:
        return {m["name"] for m in tags(endpoints) if m.get("name")}
    except (httpx.HTTPError, providers.ProviderError, ValueError):
        return set()


def delete(model: str, endpoints: Mapping[str, dict] | None = None) -> None:
    _request("DELETE", "/api/delete", endpoints, json={"model": model})


# ─── Benchmark ───────────────────────────────────────────────


def speeds(data: dict) -> tuple[float | None, float | None]:
    """(generation, prefill) tokens per second from Ollama's timings (ns)."""

    def rate(count: object, ns: object) -> float | None:
        if not (isinstance(count, int) and isinstance(ns, (int, float)) and count > 0 and ns > 0):
            return None
        return round(count / (ns / 1e9), 2)

    return rate(data.get("eval_count"), data.get("eval_duration")), rate(data.get("prompt_eval_count"), data.get("prompt_eval_duration"))


def benchmark(model: str, endpoints: Mapping[str, dict] | None = None) -> dict:
    """Generate 128 tokens, measure speed on this machine and store it."""
    body = {"model": model, "prompt": BENCH_PROMPT, "stream": False, "options": {"num_predict": BENCH_TOKENS}}
    data = _request("POST", "/api/generate", endpoints, json=body, timeout=providers.TIMEOUT).json()
    tok_per_sec, prefill = speeds(data)
    if tok_per_sec is None:
        raise providers.ProviderError("ollama", "the benchmark returned no timings")
    ref = f"ollama:{model}"
    fingerprint = hardware.current()["fingerprint"]
    store.save_benchmark(ref, tok_per_sec, prefill, fingerprint)
    return {"model_ref": ref, "tok_per_sec": tok_per_sec, "prefill_tok_per_sec": prefill, "hw_fingerprint": fingerprint}


# ─── Pulls ───────────────────────────────────────────────────


class Throttle:
    """Lets an event through at most once per interval, or when forced."""

    def __init__(self, interval: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.interval, self.clock = interval, clock
        self.last: float | None = None

    def ready(self, force: bool = False) -> bool:
        now = self.clock()
        if not force and self.last is not None and now - self.last < self.interval:
            return False
        self.last = now
        return True


def pull(
    model: str,
    on_progress: Callable[[dict], None],
    *,
    cancel: threading.Event | None = None,
    endpoints: Mapping[str, dict] | None = None,
    interval: float = PULL_INTERVAL,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Pull a model. True when it's installed, False if cancelled.

    on_progress gets {status, completed, total} (bytes, summed over the
    model's layers) on every status change and otherwise at most once per
    interval. Cancelling closes the stream, which stops Ollama's download.
    """
    layers: dict[str, tuple[int, int]] = {}
    throttle = Throttle(interval, clock)
    current = ""
    body = {"model": model, "stream": True}
    with providers.http_client() as http, http.stream("POST", base_url(endpoints) + "/api/pull", json=body) as r:
        if r.status_code >= 400:
            r.read()
            raise _failure(r)
        for line in r.iter_lines():
            if cancel is not None and cancel.is_set():
                return False
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("error"):
                raise providers.ProviderError("ollama", str(data["error"]))
            if data.get("digest") and data.get("total"):
                layers[data["digest"]] = (int(data.get("completed") or 0), int(data["total"]))
            changed = bool(data.get("status")) and data["status"] != current
            current = data.get("status") or current
            if throttle.ready(force=changed):
                on_progress(
                    {
                        "status": current,
                        "completed": sum(c for c, _ in layers.values()),
                        "total": sum(t for _, t in layers.values()),
                    }
                )
            if current == "success":
                return True
    raise providers.ProviderError("ollama", "the download ended before it finished")


class PullJobs:
    """Pulls running in background threads, one per model.

    Progress goes to the bus as live-only pull_progress events; list() gives
    the state of every pull since startup, for clients that connect later.
    """

    def __init__(self, bus: MessageBus = message_bus) -> None:
        self.bus = bus
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._cancels: dict[str, threading.Event] = {}

    def start(self, model: str, endpoints: Mapping[str, dict] | None = None) -> dict | None:
        """Start (or resume) a pull. None if this model is already pulling."""
        with self._lock:
            job = self._jobs.get(model)
            if job and job["status"] == "pulling":
                return None
            job = {"model": model, "status": "pulling", "detail": "starting", "completed": 0, "total": 0, "error": None}
            self._jobs[model] = job
            cancel = self._cancels[model] = threading.Event()
            snapshot = dict(job)
        threading.Thread(target=self._run, args=(model, cancel, endpoints), daemon=True, name=f"pull {model}").start()
        return snapshot

    def cancel(self, model: str) -> bool:
        with self._lock:
            job = self._jobs.get(model)
            if not job or job["status"] != "pulling":
                return False
            self._cancels[model].set()
        return True

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(job) for job in self._jobs.values()]

    def _update(self, model: str, **changes) -> None:
        with self._lock:
            job = self._jobs[model]
            job.update(changes)
            snapshot = dict(job)
        percent = f" {100 * snapshot['completed'] // snapshot['total']}%" if snapshot["total"] else ""
        self.bus.publish(
            AgentMessage(
                agent_name="System",
                content=f"{model}: {snapshot['detail'] if snapshot['status'] == 'pulling' else snapshot['status']}{percent}",
                message_type="pull_progress",
                data=snapshot,
            )
        )

    def _run(self, model: str, cancel: threading.Event, endpoints: Mapping[str, dict] | None) -> None:
        def progress(p: dict) -> None:
            self._update(model, detail=p["status"], completed=p["completed"], total=p["total"])

        try:
            done = pull(model, progress, cancel=cancel, endpoints=endpoints)
            self._update(model, status="success" if done else "cancelled")
        except providers.ProviderError as e:
            self._update(model, status="error", error=str(e))
        except httpx.HTTPError as e:
            self._update(model, status="error", error=f"can't reach Ollama at {base_url(endpoints)} ({type(e).__name__})")
        except Exception as e:  # a thread must report, not die silently
            log.exception("Pull of %s failed", model)
            self._update(model, status="error", error=type(e).__name__)


PULLS = PullJobs()
