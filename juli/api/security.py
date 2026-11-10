"""
Session token auth, WebSocket origin check, security headers, rate limiting.

Auth is header-only (Authorization: Bearer), so the API isn't exposed to CSRF
and needs no CSRF tokens.
"""

import math
import os
import secrets
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

DEFAULT_ALLOWED_ORIGINS = [
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (3000, 8000)
]

API_CSP = "default-src 'none'; frame-ancestors 'none'"


def has_valid_token(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    scheme, _, supplied = header.partition(" ")
    return scheme.lower() == "bearer" and token_matches(request.app.state.token, supplied)


def require_token(request: Request) -> None:
    """Dependency for every /api route except health."""
    if not has_valid_token(request):
        raise HTTPException(401, "Missing or invalid session token", headers={"WWW-Authenticate": "Bearer"})


def token_matches(expected: str, supplied: str | None) -> bool:
    if not supplied or not isinstance(supplied, str):
        return False
    return secrets.compare_digest(expected.encode(), supplied.encode())


def allowed_origins() -> set[str]:
    raw = os.environ.get("JULI_ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return set(origins or DEFAULT_ALLOWED_ORIGINS)


def origin_allowed(origin: str | None) -> bool:
    """Browsers always send Origin on WebSockets; non-browser clients may not."""
    return origin is None or origin.rstrip("/") in allowed_origins()


async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = API_CSP
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ─── Rate limiting ───────────────────────────────────────────

WINDOW_SECONDS = 60.0
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# New terminals per client per minute. WebSockets bypass the HTTP middleware,
# so /ws/terminal checks this itself.
TERMINAL_LIMIT = 10


def route_group(method: str, path: str) -> tuple[str, int] | None:
    """(group, limit per minute) for a request, or None if it isn't limited."""
    if not path.startswith("/api/") or method not in MUTATING:
        return None
    if method == "POST" and path == "/api/task":
        return "task", 10
    if method == "POST" and path.startswith("/api/runs/") and path.endswith("/resume"):
        return "task", 10
    if method == "POST" and path.startswith("/api/runs/") and path.endswith("/chat"):
        return "chat", 30
    if method == "POST" and path.startswith("/api/runs/") and path.endswith(("/commit", "/push")):
        return "git", 10
    if path.startswith("/api/settings/keys") or path.startswith("/api/providers/endpoints"):
        return "keys", 10
    return "mutate", 60


class RateLimiter:
    """In-memory sliding window keyed by client and route group.

    Only touched from the event loop thread, so it needs no lock.
    """

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def check(self, key: tuple[str, str], limit: int, now: float | None = None) -> float:
        """Record a hit. Returns 0 if allowed, else seconds until a slot frees."""
        now = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            return hits[0] + WINDOW_SECONDS - now
        hits.append(now)
        return 0.0

    async def middleware(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        group = route_group(request.method, request.url.path)
        # Only authenticated requests count: otherwise any web page could fill
        # the user's buckets with forged requests. Unauthenticated ones get a
        # 401 from require_token, and the 256-bit token can't be brute-forced.
        if group and has_valid_token(request):
            name, limit = group
            client = request.client.host if request.client else "unknown"
            wait = self.check((client, name), limit)
            if wait > 0:
                return JSONResponse(
                    {"detail": "Too many requests"},
                    status_code=429,
                    headers={"Retry-After": str(max(1, math.ceil(wait)))},
                )
        return await call_next(request)
