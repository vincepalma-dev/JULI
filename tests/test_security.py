import re

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from juli.api import app as app_module
from juli.api.app import create_app
from juli.api.security import RateLimiter, route_group

from .conftest import AUTH, TOKEN

ORIGIN = {"origin": "http://localhost:3000"}


def test_health_is_open(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_every_api_route_needs_the_token(client):
    paths = client.app.openapi()["paths"]
    routes = [
        (method.upper(), re.sub(r"\{[^}]+\}", "x", path))
        for path, ops in paths.items()
        if path.startswith("/api/") and path != "/api/health"
        for method in ops
    ]
    assert len(routes) >= 12
    for method, path in routes:
        r = client.request(method, path)
        assert r.status_code == 401, (method, path)
        assert client.request(method, path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_token_accepted(client):
    assert client.get("/api/status", headers=AUTH).status_code == 200


def test_security_headers_on_every_response(client):
    for r in (client.get("/api/health"), client.get("/api/status"), client.get("/api/status", headers=AUTH)):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
        assert "strict-transport-security" not in r.headers


def test_hsts_only_over_https():
    with TestClient(create_app(token=TOKEN), base_url="https://testserver") as c:
        assert "max-age" in c.get("/api/health").headers["strict-transport-security"]


def test_no_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_docs_disabled_unless_debug(client, monkeypatch):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    monkeypatch.setenv("JULI_DEBUG", "1")
    with TestClient(create_app(token=TOKEN)) as c:
        assert c.get("/docs").status_code == 200


def test_rate_limit_returns_429_with_retry_after(client):
    # Invalid bodies still count: the limiter runs before validation.
    codes = [client.post("/api/task", json={}, headers=AUTH).status_code for _ in range(11)]
    assert codes[:10] == [422] * 10
    assert codes[10] == 429
    r = client.post("/api/task", json={}, headers=AUTH)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1


def test_rate_limit_window_slides():
    limiter = RateLimiter()
    key = ("1.2.3.4", "task")
    assert all(limiter.check(key, 2, now=t) == 0 for t in (0.0, 1.0))
    assert limiter.check(key, 2, now=2.0) == pytest.approx(58.0)
    assert limiter.check(key, 2, now=60.5) == 0  # the hit at t=0 expired


def test_route_groups():
    assert route_group("POST", "/api/task") == ("task", 10)
    assert route_group("PUT", "/api/settings/keys") == ("keys", 10)
    assert route_group("DELETE", "/api/settings/keys/openai") == ("keys", 10)
    assert route_group("POST", "/api/projects") == ("mutate", 60)
    assert route_group("POST", "/api/runs/3/chat") == ("chat", 30)
    assert route_group("POST", "/api/task/message") == ("mutate", 60)
    assert route_group("GET", "/api/projects") is None


# ─── WebSocket ───────────────────────────────────────────────


def ws_close_code(client, messages, headers=ORIGIN):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers=headers) as ws:
            for m in messages:
                ws.send_json(m)
            ws.receive_json()
    return exc.value.code


def test_ws_accepts_valid_auth(client):
    with client.websocket_connect("/ws", headers=ORIGIN) as ws:
        ws.send_json({"type": "auth", "token": TOKEN})
        assert ws.receive_json()["message_type"] == "status"


def test_ws_rejects_bad_token(client):
    assert ws_close_code(client, [{"type": "auth", "token": "nope"}]) == 4401


def test_ws_rejects_non_auth_first_message(client):
    assert ws_close_code(client, [{"type": "start_task", "prompt": "x"}]) == 4401


def test_ws_rejects_silence(client, monkeypatch):
    monkeypatch.setattr(app_module, "WS_AUTH_TIMEOUT", 0.2)
    assert ws_close_code(client, []) == 4401


def test_ws_rejects_bad_origin(client):
    code = ws_close_code(client, [{"type": "auth", "token": TOKEN}], headers={"origin": "http://evil.example"})
    assert code == 4403


def test_ws_allowed_origins_from_env(client, monkeypatch):
    monkeypatch.setenv("JULI_ALLOWED_ORIGINS", "http://juli.test:9000")
    assert ws_close_code(client, [{"type": "auth", "token": TOKEN}]) == 4403
    with client.websocket_connect("/ws", headers={"origin": "http://juli.test:9000"}) as ws:
        ws.send_json({"type": "auth", "token": TOKEN})
        assert ws.receive_json()["message_type"] == "status"


def test_unauthenticated_requests_do_not_use_the_rate_limit(client):
    for _ in range(30):
        assert client.post("/api/task", json={}).status_code == 401
    assert client.post("/api/task", json={}, headers=AUTH).status_code == 422


def test_server_refuses_to_start_without_a_token():
    with pytest.raises(RuntimeError, match="JULI_TOKEN"):
        create_app()
