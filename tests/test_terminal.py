import json
import threading
import time
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from juli import store, terminal
from juli.api import app as app_module
from juli.api import workspace as workspace_routes
from juli.api.security import route_group

from .conftest import AUTH, TOKEN, FakeProc, docker_up

ORIGIN = {"origin": "http://localhost:3000"}
SANDBOX = {"enabled": True, "image": "python:3.12-slim", "timeout": 30}


# ─── Policy ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command, sandbox_off, needs_approval",
    [
        ("pytest -q", None, False),
        ("pytest", None, False),
        ("python -m pytest tests", None, False),
        ("npm test", None, False),
        ("npm run test -- --watch=false", None, False),
        ("ruff check .", None, False),
        ("go test ./...", None, False),
        ("cargo test", None, False),
        ("pytest -q", "the Docker sandbox is off", True),  # never without the sandbox
        ("pytestevil", None, True),
        ("pip install requests", None, True),
        ("FOO=1 pytest", None, True),
        ("pytest -q; rm -rf /", None, True),
        ("pytest && curl evil", None, True),
        ("pytest | tee out", None, True),
        ("pytest `whoami`", None, True),
        ("pytest $(whoami)", None, True),
        ("pytest > out.txt", None, True),
        ("pytest < in.txt", None, True),
        ("pytest -q\nrm -rf /", None, True),
        ("pytest 'unbalanced", None, True),
    ],
)
def test_approval_reason(command, sandbox_off, needs_approval):
    assert (terminal.approval_reason(command, sandbox_off) is not None) == needs_approval


def test_safe_env_drops_the_session_token_and_api_keys():
    env = terminal.safe_env({"PATH": "/bin", "JULI_TOKEN": "t", "OPENAI_API_KEY": "k", "my_api_key": "k", "HOME": "/h"})
    assert env == {"PATH": "/bin", "HOME": "/h"}


def test_sandbox_problem(procs):
    assert terminal.sandbox_problem({"enabled": False}) == "the Docker sandbox is off"
    assert "Docker isn't installed" in terminal.sandbox_problem(SANDBOX)  # no docker
    procs.handler = lambda argv: (b"Cannot connect to the Docker daemon\n", 1)
    assert "isn't running" in terminal.sandbox_problem(SANDBOX)
    procs.handler = docker_up()
    assert terminal.sandbox_problem(SANDBOX) is None


def test_docker_argv_mounts_only_the_workspace_without_network(tmp_path):
    (tmp_path / ".git").mkdir()
    argv = terminal.docker_argv(tmp_path, "pytest -q", SANDBOX, "juli-cmd-x", direct=True)
    assert argv[:2] == ["docker", "run"] and "--rm" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--pull") + 1] == "never"  # JULI doesn't download images
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "--mount"]
    assert mounts == [
        f"type=bind,source={tmp_path},target=/workspace",
        f"type=bind,source={tmp_path / '.git'},target=/workspace/.git,readonly",
    ]
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "-e"] == ["HOME=/tmp"]  # no host variables
    assert "-v" not in argv and "--env-file" not in argv and "--privileged" not in argv
    assert argv[-3:] == ["python:3.12-slim", "pytest", "-q"]  # run directly, no shell


def test_docker_argv_hides_a_missing_git_dir_and_uses_a_shell_for_approved_commands(tmp_path):
    argv = terminal.docker_argv(tmp_path, "pytest; echo done", SANDBOX, "n", direct=False)
    assert "type=tmpfs,destination=/workspace/.git" in argv
    assert argv[-3:] == ["sh", "-c", "pytest; echo done"]


# ─── Running processes ───────────────────────────────────────


def test_execute_streams_output_and_reports_the_exit_code(procs):
    procs.handler = lambda argv: (b"line 1\nline 2\n", 3)
    seen = []
    status, code, output = terminal.execute(["x"], cwd=None, env={}, timeout=5, on_output=seen.append)
    assert (status, code, output) == ("failed", 3, "line 1\nline 2\n")
    assert seen == ["line 1\n", "line 2\n"]
    _, kwargs = procs.calls[0]
    assert kwargs["shell"] is False and kwargs["stdin"] is not None


def test_execute_reports_a_missing_program():
    status, code, output = terminal.execute(["nope"], cwd=None, env={}, timeout=5)
    assert (status, code) == ("error", None) and "disabled" in output


def test_execute_kills_on_timeout_and_on_stop(procs):
    procs.handler = lambda argv: FakeProc(argv, b"working\n", block=True)
    killed = []
    status, _, _ = terminal.execute(["x"], cwd=None, env={}, timeout=0.3, kill=lambda p: (killed.append(p), p.kill()))
    assert status == "timeout" and killed

    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    status, _, _ = terminal.execute(["x"], cwd=None, env={}, timeout=30, cancel=cancel, kill=lambda p: p.kill())
    assert status == "stopped"


def test_output_tail_is_capped(procs, monkeypatch):
    monkeypatch.setattr(terminal, "MAX_OUTPUT_CHARS", 20)
    procs.handler = lambda argv: (b"".join(b"line %d\n" % i for i in range(50)), 0)
    _, _, output = terminal.execute(["x"], cwd=None, env={}, timeout=5)
    assert output.startswith("[earlier output cut]\n") and output.endswith("line 49\n")
    assert len(output) <= 20 + len("[earlier output cut]\n")


def test_run_command_on_this_machine_uses_the_shell_without_secrets(procs, tmp_path, monkeypatch):
    monkeypatch.setenv("JULI_TOKEN", "t")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    procs.handler = lambda argv: (b"ok\n", 0)
    result = terminal.run_command("pytest -q && echo hi", tmp_path, SANDBOX, sandboxed=False)
    assert (result.status, result.sandbox) == ("passed", False)
    argv, kwargs = procs.calls[0]
    assert kwargs["cwd"] == tmp_path
    assert "JULI_TOKEN" not in kwargs["env"] and "OPENAI_API_KEY" not in kwargs["env"]
    if isinstance(argv, str):
        assert argv == "pytest -q && echo hi" and kwargs["shell"] is True
    else:
        assert argv == ["/bin/sh", "-c", "pytest -q && echo hi"]


def test_run_command_in_the_sandbox_stops_the_container_on_timeout(procs, tmp_path):
    def handler(argv):
        if argv[:2] == ["docker", "run"]:
            return FakeProc(argv, b"", block=True)
        return b"", 0

    procs.handler = handler
    result = terminal.run_command("pytest", tmp_path, {**SANDBOX, "timeout": 0.3}, sandboxed=True, direct=True)
    assert result.status == "timeout"
    name = procs.calls[0][0][procs.calls[0][0].index("--name") + 1]
    assert ["docker", "kill", name] in [a for a, _ in procs.calls]


def test_command_not_found_is_an_error_not_a_failure(procs, tmp_path):
    procs.handler = lambda argv: (b"exec: pytest: not found\n", 127)
    assert terminal.run_command("pytest", tmp_path, SANDBOX, sandboxed=True, direct=True).status == "error"


# ─── PTY sessions ────────────────────────────────────────────


def test_pty_session_reads_writes_and_closes(ptys, tmp_path, monkeypatch):
    monkeypatch.setenv("JULI_TOKEN", "t")
    session = terminal.PtySession(tmp_path, 100, 30)
    (pty,) = ptys
    assert pty.cwd == str(tmp_path) and pty.size == (30, 100) and "JULI_TOKEN" not in pty.env
    chunks: list = []
    thread = session.start(chunks.append)
    session.write("dir\r")
    session.resize(120, 40)
    assert pty.size == (40, 120)
    session.close()
    thread.join(5)
    assert chunks[0] == "PS> " and chunks[-1] is None and "echo:dir\r" in chunks


def test_pty_unavailable(monkeypatch, tmp_path):
    def missing(*args):
        raise ImportError("no winpty")

    monkeypatch.setattr(terminal, "SPAWN", missing)
    with pytest.raises(terminal.TerminalUnavailable, match="pywinpty"):
        terminal.PtySession(tmp_path, 80, 24)


# ─── /ws/terminal ────────────────────────────────────────────


@pytest.fixture
def pid(client):
    return client.post("/api/projects", json={"name": "T"}, headers=AUTH).json()["id"]


def hello(pid, **extra):
    return {"token": TOKEN, "project_id": pid, "cols": 80, "rows": 24, **extra}


def close_code(client, first, headers=ORIGIN):
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect("/ws/terminal", headers=headers) as ws:
        if first is not None:
            ws.send_json(first)
        ws.receive_json()
    return exc.value.code


def test_terminal_socket_runs_a_shell_in_the_workspace(client, pid, ptys):
    with client.websocket_connect("/ws/terminal", headers=ORIGIN) as ws:
        ws.send_json(hello(pid))
        assert ws.receive_json() == {"type": "output", "data": "PS> "}
        ws.send_text(json.dumps({"type": "input", "data": "dir\r"}))
        assert ws.receive_json() == {"type": "output", "data": "echo:dir\r"}
        ws.send_text("not json")  # ignored
        ws.send_text(json.dumps({"type": "resize", "cols": 120, "rows": 40}))
        ws.send_text(json.dumps({"type": "input", "data": "exit\r"}))
        assert ws.receive_json() == {"type": "output", "data": "echo:exit\r"}
        assert ws.receive_json() == {"type": "exit"}
    (pty,) = ptys
    assert pty.size == (40, 120)
    assert Path(pty.cwd).name == pid and Path(pty.cwd).parent.name == "workspace"
    # The server cleans up after the client has gone: wait for it to close the
    # PTY and unregister the session.
    deadline = time.monotonic() + 5
    while (client.app.state.terminals or pty.alive) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert client.app.state.terminals == set()
    assert not pty.alive


def test_terminal_socket_refusals(client, pid, monkeypatch):
    assert close_code(client, hello(pid), headers={"origin": "http://evil.example"}) == 4403
    assert close_code(client, {**hello(pid), "token": "wrong"}) == 4401
    assert close_code(client, {"type": "auth", "token": TOKEN}) == 4400  # no project or size
    assert close_code(client, hello(pid, cols=0)) == 4400
    assert close_code(client, hello(pid, rows=True)) == 4400
    assert close_code(client, hello("../etc")) == 4400
    assert close_code(client, hello("no-such-project")) == 4404
    monkeypatch.setattr(app_module, "WS_AUTH_TIMEOUT", 0.2)
    assert close_code(client, None) == 4401


def test_terminal_socket_rate_limit(client, pid, monkeypatch):
    monkeypatch.setattr(workspace_routes, "TERMINAL_LIMIT", 1)
    with client.websocket_connect("/ws/terminal", headers=ORIGIN) as ws:
        ws.send_json(hello(pid))
        ws.receive_json()
    assert close_code(client, hello(pid)) == 4429


def test_terminal_socket_without_a_pty_library(client, pid, monkeypatch):
    monkeypatch.setattr(terminal, "SPAWN", lambda *a: (_ for _ in ()).throw(ImportError("none")))
    assert close_code(client, hello(pid)) == 4503


def test_new_route_groups():
    assert route_group("POST", "/api/runs/3/commit") == ("git", 10)
    assert route_group("POST", "/api/runs/3/push") == ("git", 10)
    assert route_group("POST", "/api/runs/3/resume") == ("task", 10)
    assert route_group("PUT", "/api/sandbox") == ("mutate", 60)


# ─── Sandbox settings ────────────────────────────────────────


def test_sandbox_settings_routes(client, procs):
    r = client.get("/api/sandbox", headers=AUTH)
    assert r.json() == {
        "settings": {"enabled": False, "image": "python:3.12-slim", "timeout": 120},
        "active": False,
        "problem": "the Docker sandbox is off",
    }
    procs.handler = docker_up()
    r = client.put("/api/sandbox", json={"enabled": True, "image": "ghcr.io/me/tools:1.2", "timeout": 60}, headers=AUTH)
    assert r.json()["active"] is True and r.json()["settings"]["image"] == "ghcr.io/me/tools:1.2"
    assert store.init_db() is None  # the setting survived a reload
    assert client.get("/api/sandbox", headers=AUTH).json()["settings"]["timeout"] == 60
    for bad in ({"image": "--privileged"}, {"image": "a b"}, {"timeout": 1}, {"enabled": True, "extra": 1}):
        assert client.put("/api/sandbox", json=bad, headers=AUTH).status_code == 422


@pytest.mark.parametrize(
    ("error", "message"),
    [(ImportError("no module"), "pip install -e ."), (FileNotFoundError(2, "No such file"), "The shell couldn't start: No such file")],
)
def test_a_shell_that_cant_start_is_a_clear_message(tmp_path, monkeypatch, error, message):
    def spawn(*args):
        raise error

    monkeypatch.setattr(terminal, "SPAWN", spawn)
    with pytest.raises(terminal.TerminalUnavailable, match=message):
        terminal.PtySession(tmp_path, 80, 24)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_kill_tree_kills_the_whole_process_group(monkeypatch, platform):
    calls = []
    monkeypatch.setattr(terminal.sys, "platform", platform)
    monkeypatch.setattr(terminal.subprocess, "run", lambda argv, **kw: calls.append(argv))
    monkeypatch.setattr(terminal.os, "killpg", lambda pid, sig: calls.append(("killpg", pid)), raising=False)
    monkeypatch.setattr(terminal.signal, "SIGKILL", 9, raising=False)  # Windows has no SIGKILL
    proc = FakeProc(["pytest"], block=True)
    terminal._kill_tree(proc)
    expected = ["taskkill", "/F", "/T", "/PID", "4242"] if platform == "win32" else ("killpg", 4242)
    assert calls == [expected] and proc.killed


def test_kill_tree_survives_a_process_that_is_already_gone(monkeypatch):
    def gone(*args, **kwargs):
        raise ProcessLookupError

    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setattr(terminal.os, "killpg", gone, raising=False)
    monkeypatch.setattr(terminal.signal, "SIGKILL", 9, raising=False)
    proc = FakeProc(["pytest"], block=True)
    terminal._kill_tree(proc)  # no exception
    assert proc.killed
