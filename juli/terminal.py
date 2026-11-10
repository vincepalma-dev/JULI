"""
The IDE terminal and agent commands.

Terminal: the user's own shell in a project's workspace, on a PTY (pywinpty
on Windows, ptyprocess elsewhere). A thread reads it and hands each chunk to
a callback; the WebSocket route forwards them with call_soon_threadsafe.

Agent commands come from ```bash run blocks. An allowlisted prefix isn't
enough to trust one: test runners execute code the agents wrote (conftest.py,
a generated package.json's test script). A command runs without asking only
when it starts with an allowlisted prefix, has no shell metacharacters and
the Docker sandbox is on: only the workspace mounted (its .git read-only), no
network, no host environment variables. Everything else asks first.

Neither the terminal nor any command gets JULI's session token or API keys
from the environment. Tests replace POPEN (processes) and SPAWN (PTYs).
"""

import functools
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from juli import config

ALLOWED_PREFIXES = ("pytest", "python -m pytest", "npm test", "npm run test", "ruff", "go test", "cargo test")
METACHARACTERS = frozenset(";&|`$<>\n\r")
MAX_COMMAND_CHARS = 2000
MAX_OUTPUT_CHARS = 12_000
DOCKER_CHECK_TIMEOUT = 15
# Exit codes that mean the command never really ran: docker itself failed
# (125), it can't be run (126), it wasn't found (127; 9009 in cmd.exe).
NOT_RUN = {125, 126, 127, 9009}

POPEN: Callable[..., Any] = subprocess.Popen


def safe_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment without JULI's own variables (the session token) or API keys."""
    env = dict(os.environ if base is None else base)
    return {k: v for k, v in env.items() if not (k.upper().startswith("JULI_") or k.upper().endswith("_API_KEY"))}


# ─── Agent command policy ────────────────────────────────────


def sandbox_settings(settings: dict) -> dict:
    return {**config.DEFAULT_SANDBOX, **(settings.get("sandbox") or {})}


def sandbox_problem(cfg: dict) -> str | None:
    """Why the Docker sandbox can't be used, or None when it's on and Docker answers."""
    if not cfg.get("enabled"):
        return "the Docker sandbox is off"
    status, _, _ = execute(["docker", "version", "--format", "{{.Server.Version}}"], cwd=None, env=safe_env(), timeout=DOCKER_CHECK_TIMEOUT)
    return None if status == "passed" else "Docker isn't installed or isn't running, so the sandbox is off"


def approval_reason(command: str, sandbox_off: str | None) -> str | None:
    """Why a command has to be approved before it runs, or None if it may run on its own."""
    if not any(command == p or command.startswith(p + " ") for p in ALLOWED_PREFIXES):
        return "it isn't one of the test and lint commands"
    if any(c in METACHARACTERS for c in command):
        return "it has shell metacharacters"
    if sandbox_off:
        return sandbox_off
    try:
        shlex.split(command)
    except ValueError:
        return "its quoting is unbalanced"
    return None


@dataclass
class CommandResult:
    command: str
    status: str  # passed, failed, timeout, stopped, error (it never ran), denied
    exit_code: int | None = None
    output: str = ""
    sandbox: bool = False
    seconds: float = 0.0


def docker_argv(base: Path, command: str, cfg: dict, name: str, *, direct: bool) -> list[str]:
    """`docker run` for a command: the workspace is the only mount (its .git
    read-only, or hidden if there's none), no network, no host variables."""
    if "," in str(base):
        raise ValueError("The workspace path can't contain a comma for the Docker sandbox")
    git_dir = base / ".git"
    git_mount = (
        f"type=bind,source={git_dir},target=/workspace/.git,readonly" if git_dir.is_dir() else "type=tmpfs,destination=/workspace/.git"
    )
    argv = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "512",
        "--memory", "2g",
        "--read-only", "--tmpfs", "/tmp",
        "-e", "HOME=/tmp",
        "--mount", f"type=bind,source={base},target=/workspace",
        "--mount", git_mount,
        "-w", "/workspace",
    ]  # fmt: skip
    if sys.platform != "win32":  # files it creates belong to the user, not root
        argv += ["--user", f"{os.getuid()}:{os.getgid()}"]
    argv.append(cfg["image"])
    # A command that may run on its own is executed directly, without a shell.
    argv += shlex.split(command) if direct else ["sh", "-c", command]
    return argv


def run_command(
    command: str,
    base: Path,
    cfg: dict,
    *,
    sandboxed: bool,
    direct: bool = False,
    cancel: threading.Event | None = None,
    on_output: Callable[[str], None] | None = None,
) -> CommandResult:
    """Run an agent command in the workspace: in the sandbox, or (approved) on this machine."""
    start = time.monotonic()
    kill: Callable[[Any], None] | None = None
    argv: list[str] | str
    if sandboxed:
        name = f"juli-cmd-{uuid.uuid4().hex[:12]}"
        argv = docker_argv(base, command, cfg, name, direct=direct)
        kill = functools.partial(_stop_container, name)
    else:
        # The user approved this exact text as a shell command.
        argv = command if os.name == "nt" else ["/bin/sh", "-c", command]
    status, code, output = execute(argv, cwd=base, env=safe_env(), timeout=int(cfg["timeout"]), cancel=cancel, on_output=on_output, kill=kill)
    if status == "failed" and code in NOT_RUN:
        status = "error"
    return CommandResult(command, status, code, output, sandboxed, round(time.monotonic() - start, 2))


# ─── Processes ───────────────────────────────────────────────


class _Tail:
    """The last `limit` characters of a stream."""

    def __init__(self, limit: int | None = None) -> None:
        self.limit = limit or MAX_OUTPUT_CHARS
        self.parts: deque[str] = deque()
        self.size = 0
        self.cut = False

    def add(self, text: str) -> None:
        self.parts.append(text)
        self.size += len(text)
        while len(self.parts) > 1 and self.size - len(self.parts[0]) >= self.limit:
            self.size -= len(self.parts.popleft())
            self.cut = True

    def text(self) -> str:
        joined = "".join(self.parts)
        if len(joined) > self.limit:
            joined, self.cut = joined[-self.limit :], True
        return ("[earlier output cut]\n" if self.cut else "") + joined


def _group() -> dict:
    """Start the process in its own group so a kill reaches its children."""
    return {} if sys.platform == "win32" else {"start_new_session": True}


def _kill_tree(proc: Any) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _stop_container(name: str, proc: Any) -> None:
    # Killing the docker client doesn't stop the container; kill it by name.
    execute(["docker", "kill", name], cwd=None, env=safe_env(), timeout=DOCKER_CHECK_TIMEOUT)
    try:
        proc.kill()
    except OSError:
        pass


def execute(
    argv: list[str] | str,
    *,
    cwd: Path | None,
    env: dict[str, str],
    timeout: float,
    cancel: threading.Event | None = None,
    on_output: Callable[[str], None] | None = None,
    kill: Callable[[Any], None] | None = None,
) -> tuple[str, int | None, str]:
    """Run a process, streaming its output: (status, exit code, output tail).

    The status is passed, failed, timeout, stopped (cancel was set) or error
    (it couldn't start). A string argv runs in the platform shell.
    """
    try:
        proc = POPEN(
            argv,
            cwd=cwd,
            env=env,
            shell=isinstance(argv, str),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **_group(),
        )
    except OSError as e:
        return "error", None, e.strerror or str(e)

    why: list[str] = []
    done = threading.Event()

    def watch() -> None:
        deadline = time.monotonic() + timeout
        while not done.wait(0.1):
            if cancel is not None and cancel.is_set():
                why.append("stopped")
            elif time.monotonic() >= deadline:
                why.append("timeout")
            else:
                continue
            (kill or _kill_tree)(proc)
            return

    threading.Thread(target=watch, daemon=True).start()
    tail = _Tail()
    try:
        for raw in iter(proc.stdout.readline, b""):
            text = raw.decode("utf-8", "replace")
            tail.add(text)
            if on_output:
                on_output(text)
        code = proc.wait()
    finally:
        done.set()
    status = why[0] if why else "passed" if code == 0 else "failed"
    return status, code, tail.text()


# ─── PTY sessions ────────────────────────────────────────────


class TerminalUnavailable(RuntimeError):
    """No PTY could be started."""


def default_shell() -> list[str]:
    if os.name == "nt":
        return ["powershell.exe", "-NoLogo"]
    return [os.environ.get("SHELL") or "/bin/sh"]


def _spawn(argv: list[str], cwd: str, env: dict[str, str], rows: int, cols: int) -> Any:
    if sys.platform == "win32":
        from winpty import PtyProcess  # type: ignore[import-untyped, import-not-found, unused-ignore]
    else:
        from ptyprocess import PtyProcessUnicode as PtyProcess  # type: ignore[import-untyped, import-not-found, unused-ignore]
    return PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))


SPAWN: Callable[..., Any] = _spawn


class PtySession:
    """The user's shell on a PTY, started in a workspace folder."""

    def __init__(self, cwd: Path, cols: int, rows: int, argv: list[str] | None = None) -> None:
        env = safe_env()
        if os.name != "nt":
            env.setdefault("TERM", "xterm-256color")
        try:
            self.pty = SPAWN(argv or default_shell(), str(cwd), env, rows, cols)
        except ImportError:
            raise TerminalUnavailable("The terminal needs pywinpty (Windows) or ptyprocess: pip install -r requirements.txt") from None
        except OSError as e:
            raise TerminalUnavailable(f"The shell couldn't start: {e.strerror or e}") from None
        self._closed = False

    def start(self, on_output: Callable[[str | None], None]) -> threading.Thread:
        """Read on a thread. on_output gets each chunk, then None once the shell exits."""

        def read() -> None:
            try:
                while True:
                    data = self.pty.read(4096)
                    if data:
                        on_output(data)
                    elif not self.pty.isalive():
                        break
            except (EOFError, OSError):
                pass
            finally:
                on_output(None)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        return thread

    def write(self, data: str) -> None:
        self.pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        self.pty.setwinsize(rows, cols)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.pty.terminate(force=True)
        except (OSError, EOFError):  # already gone; nothing else to clean up
            pass
