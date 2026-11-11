"""
The harness around each agent turn: middleware for model calls and tool
calls, and the shapes they pass along.

A middleware is a function (call, call_next) -> result. It may check the
call, pass it on with call_next (the next layer, and in the end the model or
the tool), and look at or change the result. A run keeps two ordered lists,
model_middleware and tool_middleware, outermost first, which can be
extended; chain() makes one handler of a list and the innermost step.

Default model layers: Stop, Privacy Mode, the token and budget caps, then
usage and cost. Every model call goes through them, each round of a tool
loop included. Default tool layers: Stop, the role's tool permissions, the
repeat guard, then the tool events the dashboard shows.
"""

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from juli import providers, tools

# Repeating the same call (same tool, same arguments) this often without a
# change in between is a loop; the next one isn't run.
MAX_REPEATS = 2


class Stopped(Exception):
    """The run ends early, keeping its partial output."""


@dataclass
class ModelCall:
    run: Any  # the engine's Run
    agent: Any  # the engine's Agent
    messages: list[dict]
    tools: list[dict] = field(default_factory=list)  # schemas offered this round
    est_in: int = 0  # estimated input tokens


@dataclass
class Reply:
    text: str = ""
    tool_calls: list[providers.ToolCall] = field(default_factory=list)
    usage: providers.Usage | None = None
    cut: str | None = None  # the cap that cut the stream short


@dataclass
class ToolResult:
    output: str
    status: str = "ok"  # ok, error, denied
    server: str | None = None  # the MCP server, for MCP tools


@dataclass
class ToolContext:
    run: Any
    agent: Any
    call: providers.ToolCall
    args: dict
    allowed: set[str]  # the tools this turn may use
    seen: Counter = field(default_factory=Counter)  # identical calls since the last change
    activity: str = "working"  # what the agent's turn is doing, for the live line


Middleware = Callable[[Any, Callable[[Any], Any]], Any]


def chain(middleware: list[Middleware], handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """One handler: the first middleware outermost, `handler` innermost."""
    for layer in reversed(middleware):
        handler = _wrap(layer, handler)
    return handler


def _wrap(layer: Middleware, inner: Callable[[Any], Any]) -> Callable[[Any], Any]:
    return lambda call: layer(call, inner)


def estimate_tokens(chars: int) -> int:
    return -(-chars // 4)


def estimate(messages: list[dict]) -> int:
    """Input tokens, estimated from the characters sent, tool calls included."""
    chars = 0
    for m in messages:
        chars += len(m.get("content") or "")
        chars += sum(len(c["name"]) + len(c["arguments"]) for c in m.get("tool_calls") or [])
    return estimate_tokens(chars)


# ─── Model call layers ───────────────────────────────────────


def stop_guard(call: ModelCall, call_next: Callable[[ModelCall], Reply]) -> Reply:
    if call.run.cancel.is_set():
        raise Stopped("stopped by the user")
    reply = call_next(call)
    if call.run.cancel.is_set():
        raise Stopped("stopped by the user")
    return reply


def privacy_guard(call: ModelCall, call_next: Callable[[ModelCall], Reply]) -> Reply:
    run = call.run
    if run.privacy and not providers.is_local(call.agent.model, run.endpoints):
        raise providers.PrivacyViolation(f"Privacy Mode is on: {call.agent.model} is a cloud model")
    return call_next(call)


def cap_guard(call: ModelCall, call_next: Callable[[ModelCall], Reply]) -> Reply:
    """Before the call: would it pass a cap? After: did a cap cut it short?"""
    run = call.run
    cap = run.cap_hit(call.agent.model, call.est_in, call.agent.max_tokens or 0)
    if cap:
        run.limit_reached(cap)
    reply = call_next(call)
    if reply.cut:
        run.limit_reached(reply.cut)
    return reply


def usage_recorder(call: ModelCall, call_next: Callable[[ModelCall], Reply]) -> Reply:
    """Adds the call's tokens and cost to the run, estimating them when the stream was cut short."""
    reply = call_next(call)
    run = call.run
    if reply.usage is None and (reply.text or reply.tool_calls):
        tokens_out = estimate_tokens(len(reply.text) + sum(len(c.arguments) for c in reply.tool_calls))
        reply.usage = providers.Usage(call.est_in, tokens_out, providers.cost(call.agent.model, call.est_in, tokens_out, run.endpoints))
    if reply.usage is not None:
        run.record_usage(call.agent, reply.text, reply.usage)
    return reply


MODEL_MIDDLEWARE: list[Middleware] = [stop_guard, privacy_guard, cap_guard, usage_recorder]


# ─── Tool call layers ────────────────────────────────────────


def tool_stop_guard(ctx: ToolContext, call_next: Callable[[ToolContext], ToolResult]) -> ToolResult:
    if ctx.run.cancel.is_set():
        raise Stopped("stopped by the user")
    return call_next(ctx)


def permission_guard(ctx: ToolContext, call_next: Callable[[ToolContext], ToolResult]) -> ToolResult:
    """Only the turn's own tools run, whatever name the model asks for."""
    if ctx.call.name not in ctx.allowed:
        return ToolResult(f"{ctx.agent.name} can't use '{ctx.call.name}' in this step.", "error")
    return call_next(ctx)


def repeat_guard(ctx: ToolContext, call_next: Callable[[ToolContext], ToolResult]) -> ToolResult:
    """A third identical call with no change in between isn't run."""
    key = (ctx.call.name, json.dumps(ctx.args, sort_keys=True))
    if ctx.seen[key] >= MAX_REPEATS:
        return ToolResult(
            f"You already made this exact call {MAX_REPEATS} times and nothing has changed since, so it wasn't run again. "
            "Use the result you have, or try something else.",
            "error",
        )
    ctx.seen[key] += 1
    result = call_next(ctx)
    if ctx.call.name in tools.CHANGES and result.status == "ok":
        ctx.seen.clear()
    return result


# Tools whose own events already show them: run_command (command events) and write_file (files events).
OWN_EVENTS = ("run_command", "write_file")


def tool_events(ctx: ToolContext, call_next: Callable[[ToolContext], ToolResult]) -> ToolResult:
    """tool_start before the call, tool after it, for the timeline and the terminal's Agent tab."""
    if ctx.call.name in OWN_EVENTS:
        return call_next(ctx)
    run, name = ctx.run, ctx.call.name
    if run.replaying:  # its events went out the first time
        return call_next(ctx)
    data = {"tool": name, "call_id": ctx.call.id, "args": ctx.args}
    run.publish(ctx.agent.name, summary(name, ctx.args), "tool_start", data=data)
    started = time.monotonic()
    result = call_next(ctx)
    seconds = round(time.monotonic() - started, 2)
    run.publish(
        ctx.agent.name,
        summary(name, ctx.args),
        "tool",
        data={**data, "status": result.status, "output": result.output, "seconds": seconds, "server": result.server},
    )
    return result


TOOL_MIDDLEWARE: list[Middleware] = [tool_stop_guard, permission_guard, repeat_guard, tool_events]


def summary(name: str, args: dict) -> str:
    """A short line for a tool call: the tool and its key argument."""
    key = next((args[k] for k in ("path", "text", "directory", "to", "command") if isinstance(args.get(k), str) and args[k]), "")
    return f"{name} {key}".strip()[:200]


# ─── Messages ────────────────────────────────────────────────


def assistant_message(reply: Reply) -> dict:
    return {
        "role": "assistant",
        "content": reply.text,
        "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in reply.tool_calls],
    }


def tool_message(call: providers.ToolCall, result: ToolResult) -> dict:
    prefix = "" if result.status == "ok" else f"[{result.status}] "
    return {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": prefix + result.output}
