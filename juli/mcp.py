"""
A small Model Context Protocol client: JSON-RPC 2.0 over stdio or streamable
HTTP, enough to list a server's tools and call them.

Servers come from settings ("mcp_servers"), name -> {transport, command or
url, enabled, sandbox, trusted_tools, roles, token_env}. A server's token, if
it needs one, lives in the keychain as "mcp:<name>", never in settings.json:
an HTTP server gets it as a bearer token, a stdio server as the environment
variable named by token_env.

A stdio server is a child process with safe_env() (no JULI_* variables, no
API keys). With its sandbox switch on, it runs in the Docker sandbox: no
network, only the workspace mounted, and the image must already be on this
machine (--pull never).

Privacy Mode: an HTTP server must be on this machine or the LAN, and a stdio
server must run in the sandbox. Any other server doesn't start.

Everything a server returns is untrusted input for the model, like a file.
"""

import json
import logging
import queue
import re
import shlex
import shutil
import subprocess
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from juli import keystore, providers, terminal

log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
START_TIMEOUT = 30.0
CALL_TIMEOUT = 300.0
MAX_TOOLS = 100
PREFIX = "mcp__"

# Test seam: tests replace it to start fake servers.
POPEN: Callable[..., Any] = subprocess.Popen


class McpError(RuntimeError):
    """A server couldn't start, or a request to it failed."""


@dataclass
class McpTool:
    server: str
    name: str  # the server's own name for the tool
    description: str
    parameters: dict

    @property
    def full_name(self) -> str:
        return tool_name(self.server, self.name)

    def schema(self) -> dict:
        return {"name": self.full_name, "description": self.description, "parameters": self.parameters}


def tool_name(server: str, tool: str) -> str:
    """The namespaced name models see, e.g. mcp__github__create_issue (at most 64 characters)."""
    return (PREFIX + server + "__" + re.sub(r"[^A-Za-z0-9_-]", "_", tool))[:64]


def token_key(name: str) -> str:
    """The keychain entry for a server's token."""
    return f"mcp:{name}"


def start_problem(cfg: dict, *, privacy: bool, sandbox_off: str | None) -> str | None:
    """Why a server may not start in this run, or None."""
    if cfg.get("transport") == "http":
        if privacy and not providers.is_local_url(cfg.get("url") or ""):
            return "Privacy Mode is on and its URL isn't on this machine or the LAN"
        return None
    if cfg.get("sandbox"):
        return f"it runs in the sandbox, and {sandbox_off}" if sandbox_off else None
    if privacy:
        return "Privacy Mode is on, and outside the sandbox it would have network access"
    return None


def _text(result: dict) -> str:
    """A tools/call result as text: text blocks as they are, anything else named.
    A malformed result (content as a string, or items that aren't blocks) is read as far as it can be."""
    content = result.get("content") or []
    if isinstance(content, str):
        return content
    parts = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        else:
            parts.append(f"[{block.get('type', 'unknown')} content]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"]))
    return "\n".join(parts)


# ─── Transports ──────────────────────────────────────────────


class _Stdio:
    """Newline-delimited JSON-RPC over a child process's stdin and stdout."""

    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path | None, container: str | None) -> None:
        self.container = container
        try:
            self.proc = POPEN(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise McpError(f"it couldn't start: {e.strerror or e}") from None
        self.inbox: queue.Queue = queue.Queue()
        self.errors: deque[str] = deque(maxlen=20)
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_errors, daemon=True).start()

    def _read(self) -> None:
        for raw in iter(self.proc.stdout.readline, b""):
            try:
                message = json.loads(raw)
            except ValueError:
                continue  # servers may log to stdout; only JSON-RPC counts
            if isinstance(message, dict):  # a log line can be valid JSON too, like 42 or "ready"
                self.inbox.put(message)
        self.inbox.put(None)  # the server exited

    def _read_errors(self) -> None:
        for raw in iter(self.proc.stderr.readline, b""):
            self.errors.append(raw.decode("utf-8", "replace").rstrip())

    def stderr(self) -> str:
        return "\n".join(self.errors)

    def send(self, message: dict) -> None:
        with self.lock:
            try:
                self.proc.stdin.write(json.dumps(message).encode() + b"\n")
                self.proc.stdin.flush()
            except OSError:
                raise McpError(self._exited()) from None

    def _exited(self) -> str:
        tail = self.stderr().splitlines()
        return "the server exited" + (f": {tail[-1]}" if tail else "")

    def request(self, message: dict, timeout: float, cancel: threading.Event | None) -> dict:
        self.send(message)
        waited = 0.0
        while True:
            if cancel is not None and cancel.is_set():
                self.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": message["id"]}})
                raise McpError("stopped")
            try:
                reply = self.inbox.get(timeout=0.2)
            except queue.Empty:
                waited += 0.2
                if waited >= timeout:
                    raise McpError(f"no answer within {timeout:.0f} s") from None
                continue
            if reply is None:
                raise McpError(self._exited())
            if reply.get("id") == message["id"] and "method" not in reply:
                return reply
            if "method" in reply and "id" in reply:  # the server asks us something: we offer nothing
                self.send({"jsonrpc": "2.0", "id": reply["id"], "error": {"code": -32601, "message": "Not supported by JULI"}})

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        if self.container:
            terminal.stop_container(self.container, self.proc)
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()


class _Http:
    """Streamable HTTP: each JSON-RPC message is a POST; the answer is JSON or an SSE stream."""

    def __init__(self, url: str, token: str | None) -> None:
        self.url, self.token = url, token
        self.session: str | None = None
        self.version: str | None = None
        self.http = providers.http_client()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.version:
            headers["MCP-Protocol-Version"] = self.version
        return headers

    def send(self, message: dict) -> None:
        try:
            self.http.post(self.url, json=message, headers=self._headers(), timeout=START_TIMEOUT)
        except providers.httpx.HTTPError as e:
            raise McpError(f"can't reach it ({type(e).__name__})") from None

    def _post(self, message: dict, timeout: float) -> providers.httpx.Response:
        try:
            return self.http.post(self.url, json=message, headers=self._headers(), timeout=timeout)
        except providers.httpx.HTTPError as e:
            raise McpError(f"can't reach it ({type(e).__name__})") from None

    def request(self, message: dict, timeout: float, cancel: threading.Event | None) -> dict:
        if cancel is None:
            response = self._post(message, timeout)
        else:
            # The POST runs on a worker so Stop ends the wait at once; an abandoned
            # request finishes or times out on its own (closing the client ends it too).
            done: dict[str, Any] = {}

            def post() -> None:
                try:
                    done["response"] = self._post(message, timeout)
                except (McpError, RuntimeError) as e:  # RuntimeError: the client was closed meanwhile
                    done["error"] = e

            worker = threading.Thread(target=post, daemon=True)
            worker.start()
            while worker.is_alive():
                if cancel.is_set():
                    raise McpError("stopped")
                worker.join(0.2)
            if "response" not in done:
                raise McpError(str(done.get("error") or "the request failed"))
            response = done["response"]
        if response.status_code >= 400:
            raise McpError(f"HTTP {response.status_code}")
        self.session = response.headers.get("mcp-session-id") or self.session
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            for event in response.text.split("\n\n"):
                data = "\n".join(line[5:].strip() for line in event.splitlines() if line.startswith("data:"))
                try:
                    reply = json.loads(data) if data else None
                except ValueError:
                    continue
                if isinstance(reply, dict) and reply.get("id") == message["id"]:
                    return reply
            raise McpError("the answer had no result")
        try:
            reply = response.json()
        except ValueError:
            raise McpError("the answer wasn't JSON") from None
        if not isinstance(reply, dict):
            raise McpError("the answer wasn't a JSON-RPC response")
        return reply

    def stderr(self) -> str:
        return ""

    def close(self) -> None:
        if self.session:
            try:
                self.http.delete(self.url, headers=self._headers(), timeout=5)
            except providers.httpx.HTTPError:
                pass
        self.http.close()


# ─── Servers ─────────────────────────────────────────────────


class Server:
    """One configured server, started for a run and closed when it ends."""

    def __init__(self, name: str, cfg: dict) -> None:
        self.name, self.cfg = name, cfg
        self.sandboxed = cfg.get("transport") != "http" and bool(cfg.get("sandbox"))
        self.trusted = set(cfg.get("trusted_tools") or [])
        self.transport: _Stdio | _Http | None = None
        self._ids = 0

    def start(self, workspace_dir: Path | None, sandbox_cfg: dict) -> list[McpTool]:
        """Connect, initialize and list the tools. McpError if it can't."""
        token = keystore.get_key(token_key(self.name))
        if self.cfg.get("transport") == "http":
            self.transport = _Http(self.cfg["url"], token)
        else:
            env = terminal.safe_env()
            if token and self.cfg.get("token_env"):
                env[self.cfg["token_env"]] = token
            command = list(self.cfg.get("command") or [])
            if not command:
                raise McpError("it has no command")
            container = None
            if self.sandboxed:
                if workspace_dir is None:
                    raise McpError("the sandbox needs the project's workspace")
                container = f"juli-mcp-{uuid.uuid4().hex[:12]}"
                # `-e NAME` passes the token from the docker client's environment, so it never shows in argv.
                names = [self.cfg["token_env"]] if token and self.cfg.get("token_env") else []
                argv = terminal.docker_argv(
                    workspace_dir, shlex.join(command), sandbox_cfg, container, direct=True, interactive=True, env=names
                )
            else:
                argv = [shutil.which(command[0]) or command[0], *command[1:]]
            self.transport = _Stdio(argv, env, workspace_dir, container)
        try:
            result = self._request(
                "initialize",
                {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "juli", "version": "1"}},
                START_TIMEOUT,
            )
            if isinstance(self.transport, _Http):
                self.transport.version = str(result.get("protocolVersion") or PROTOCOL_VERSION)
            self.transport.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return self._list_tools()
        except McpError:
            self.close()
            raise

    def stderr(self) -> str:
        return self.transport.stderr() if self.transport else ""

    def _request(self, method: str, params: dict, timeout: float, cancel: threading.Event | None = None) -> dict:
        assert self.transport is not None
        self._ids += 1
        reply = self.transport.request({"jsonrpc": "2.0", "id": self._ids, "method": method, "params": params}, timeout, cancel)
        if reply.get("error"):
            error = reply["error"]
            raise McpError(str(error.get("message") if isinstance(error, dict) else error)[:500])
        result = reply.get("result")
        if not isinstance(result, dict):
            raise McpError(f"{method} returned no result")
        return result

    def _list_tools(self) -> list[McpTool]:
        found: list[McpTool] = []
        cursor = None
        while len(found) < MAX_TOOLS:
            result = self._request("tools/list", {"cursor": cursor} if cursor else {}, START_TIMEOUT)
            for tool in result.get("tools") or []:
                if isinstance(tool, dict) and tool.get("name"):
                    schema = tool.get("inputSchema")
                    if not isinstance(schema, dict):
                        schema = {"type": "object", "properties": {}}
                    found.append(McpTool(self.name, str(tool["name"]), str(tool.get("description") or ""), schema))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return found[:MAX_TOOLS]

    def call(self, tool: str, args: dict, cancel: threading.Event | None = None) -> tuple[str, bool]:
        """(the result as text, whether the server reports an error)."""
        result = self._request("tools/call", {"name": tool, "arguments": args}, CALL_TIMEOUT, cancel)
        return _text(result), bool(result.get("isError"))

    def close(self) -> None:
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                log.exception("Closing MCP server %s failed", self.name)
            self.transport = None
