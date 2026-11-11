"""
The lean engine: Plan -> Code<->Review -> custom roles -> Test -> Docs.

An agent turn is a tool loop: a streamed model call, then the tools it
asked for, then the next call with their results, until it answers without
tools or uses up its tool rounds. While a call streams, the turn publishes
chunk events; when it ends, one agent message with its model, tokens and
cost. Every call and every tool goes through the run's middleware (see
juli.harness). The crew and the optional limits come from settings.

Tools depend on the role (juli.tools), and MCP servers add more (juli.mcp).
An agent can hand work to a colleague: the colleague takes a turn, and its
reply is the handoff's result. Models without tool calling use the text
protocol below instead.

Optionally, the crew discusses the plan before coding, and the user can
send notes mid-run that every later agent sees. A run can pause for a
decision (plan approval, or a key that is missing, invalid or out of credit)
and can be stopped at any time. The API reaches the active run through
stop(), decide() and say(). follow_up() answers questions about a finished run.

Files in the coder's, tester's, docs' and custom roles' replies land in the
project's workspace. Commands in ```bash run blocks run there (asking first
unless the sandbox makes that unnecessary); a failure goes back to the coder
for one fix pass.

After every step (a turn, a reply that called tools, a tool, a decision, a
command) the run saves a checkpoint. A resumed run replays the saved steps
without calling any model or running any tool or command, then continues
live.
"""

import json
import logging
import queue
import re
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from juli import config, harness, mcp, providers, roles, store, terminal, tools, workspace
from juli.bus import AgentMessage, MessageBus, message_bus
from juli.harness import Stopped, ToolResult

log = logging.getLogger(__name__)

VERDICT = re.compile(r"VERDICT:\s*(APPROVED|CHANGES REQUESTED)", re.IGNORECASE)
PLAN_VERDICT = re.compile(r"PLAN:\s*(AGREED|CHANGES NEEDED)", re.IGNORECASE)

# Which roles take part in each mode, in pipeline order.
MODE_ROLES = {
    "full": ("planner", "coder", "reviewer", "custom", "tester", "docs"),
    "code": ("planner", "coder", "reviewer"),
    "plan": ("planner", "docs"),
    "review": ("reviewer",),
}

# Turns whose fenced blocks with a path are written to the workspace (by role or protocol).
WRITES_FILES = ("coder", "tester", "docs", "custom", "fix")
MAX_COMMANDS_PER_TURN = 5
MAX_TOOL_CALLS_PER_REPLY = 8
CHECKPOINT_VERSION = 1

COMMAND_STATUS = {
    "passed": "Passed",
    "failed": "Failed",
    "timeout": "Timed out",
    "error": "Didn't run",
    "denied": "Denied",
}


@dataclass
class Agent:
    name: str
    role: str
    model: str
    prompt: str
    max_tokens: int | None = None
    num_ctx: int | None = None
    max_tool_rounds: int | None = None  # None: the run's setting

    def summary(self) -> dict:
        return {"name": self.name, "role": self.role, "model": self.model, "max_tokens": self.max_tokens}


@dataclass
class RunResult:
    status: str  # complete, stopped, error
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


def build_crew(settings: dict) -> list[Agent]:
    """The crew, in settings order, from each agent's saved configuration."""
    crew = []
    for name, cfg in settings.get("agents", {}).items():
        if not isinstance(cfg, dict):
            continue
        crew.append(
            Agent(
                name=name,
                role=roles.role_of(name, cfg),
                model=cfg.get("model") or "",
                prompt=cfg.get("prompt") or f"You are {name}. Follow instructions precisely.",
                max_tokens=cfg.get("max_tokens") or None,
                num_ctx=cfg.get("num_ctx") or None,
                max_tool_rounds=cfg.get("max_tool_rounds") or None,
            )
        )
    return crew


def cast(crew: list[Agent], mode: str, no_devops: bool = False) -> dict[str, list[Agent]]:
    """Agents per pipeline step for a mode. The first agent of each built-in
    role fills that step; every other agent is a custom role."""
    steps: dict[str, list[Agent]] = {role: [] for role in MODE_ROLES[mode]}
    filled: set[str] = set()
    for agent in crew:
        if no_devops and agent.name == "DevOps":
            continue
        role = agent.role if agent.role != "custom" and agent.role not in filled else "custom"
        filled.add(role)
        if role in steps:
            steps[role].append(agent)
    return steps


def month_start() -> str:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def allowance_report(agents: list[Agent], settings: dict) -> tuple[list[str], list[str]]:
    """(warnings at 80%, blocks at 100%) for this month's per-key allowances."""
    allowances = settings.get("run", {}).get("allowances") or {}
    warnings, blocked = [], []
    for provider in sorted({a.model.partition(":")[0] for a in agents}):
        allowance = allowances.get(provider)
        if not allowance:
            continue
        spent = store.spend_since(provider, month_start())
        line = f"{provider} has used ${spent:.2f} of its ${allowance:.2f} monthly allowance"
        if spent >= allowance:
            blocked.append(line)
        elif spent >= 0.8 * allowance:
            warnings.append(line)
    return warnings, blocked


def review_source(project_id: str) -> str:
    """What review mode reviews: the workspace's files, or else the latest run's output."""
    files = workspace.review_text(project_id)
    if files:
        return files
    return "\n\n".join(f"### {m['agent_name']}\n\n{m['content']}" for m in store.latest_output(project_id))


def _command_report(result: terminal.CommandResult) -> str:
    status = COMMAND_STATUS.get(result.status, result.status)
    if result.exit_code is not None and result.status == "failed":
        status += f" (exit code {result.exit_code})"
    return f"$ {result.command}\n{status}\n\n{result.output}".rstrip()


def _brief(*sections: tuple[str, str]) -> str:
    return "\n\n".join(f"## {title}\n\n{body}" for title, body in sections if body)


def verdict(review: str) -> str | None:
    found = VERDICT.findall(review)
    return found[-1].upper() if found else None


def plan_agreed(reply: str) -> bool:
    found = PLAN_VERDICT.findall(reply)
    return bool(found) and found[-1].upper() == "AGREED"


def _transcript(replies: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"### {name}\n\n{text}" for name, text in replies)


class Run:
    def __init__(
        self,
        prompt: str,
        mode: str,
        crew: list[Agent],
        *,
        settings: dict,
        max_cycles: int = 3,
        approve_plan: bool = False,
        discussion_rounds: int | None = None,
        no_devops: bool = False,
        review_source: str = "",
        notices: list[str] | tuple[str, ...] = (),
        bus: MessageBus = message_bus,
    ) -> None:
        cfg = settings.get("run") or {}
        self.prompt, self.mode, self.bus = prompt, mode, bus
        self.crew, self.no_devops = crew, no_devops
        self.steps = cast(crew, mode, no_devops)
        self.agents = [a for step in self.steps.values() for a in step]
        self.max_cycles, self.approve_plan = max_cycles, approve_plan
        self.review_source, self.notices = review_source, list(notices)
        # Crew discussion of the plan: 0 (off) to 4 rounds; the request overrides settings.
        self.discussion_rounds = int(cfg.get("discussion_rounds") or 0) if discussion_rounds is None else discussion_rounds
        self.privacy = bool(cfg.get("privacy_mode"))
        self.budget = cfg.get("budget_usd") or None
        self.token_cap = cfg.get("token_cap") or None
        self.fallback = cfg.get("fallback_model") if cfg.get("auto_fallback") else None
        self.allowances = cfg.get("allowances") or {}
        self.endpoints = settings.get("endpoints") or {}
        self.tool_rounds = int(cfg.get("max_tool_rounds") or config.DEFAULT_RUN["max_tool_rounds"])
        handoffs = cfg.get("max_handoffs")
        self.max_handoffs = int(config.DEFAULT_RUN["max_handoffs"] if handoffs is None else handoffs)
        self.mcp_servers = {n: c for n, c in (settings.get("mcp_servers") or {}).items() if isinstance(c, dict) and c.get("enabled", True)}

        # The harness: middleware around every model call and every tool call (juli.harness).
        self.model_middleware: list[harness.Middleware] = list(harness.MODEL_MIDDLEWARE)
        self.tool_middleware: list[harness.Middleware] = list(harness.TOOL_MIDDLEWARE)
        self.handoffs = 0
        self._pairs: Counter = Counter()  # handoffs between each pair of agents, either way
        self._waiting: list[str] = []  # agents waiting on a handoff they made
        self._mcp: dict[str, mcp.Server] | None = None  # started on first use
        self._mcp_tools: dict[str, mcp.McpTool] = {}

        self.cancel = threading.Event()
        self.tokens_in = self.tokens_out = 0
        self.cost_usd = 0.0
        self._decisions: queue.Queue = queue.Queue()
        self._pending: dict | None = None
        self._lock = threading.Lock()
        self._warned: set[str] = set()
        self._notes: list[str] = []  # the user's mid-run messages

        # The workspace, set by attach() once the run has a row.
        self.sandbox = terminal.sandbox_settings(settings)
        self.project_id: str | None = None
        self.run_id: int | None = None
        self.workspace: Path | None = None
        self._sandbox_checked = False
        self._sandbox_off: str | None = None

        # Checkpointing: the steps done so far, and those still to replay when resuming.
        self.on_checkpoint: Callable[[dict, str], None] | None = None
        self.resumed = False
        self._steps: list[dict] = []
        self._replay: list[dict] = []

    def attach(self, project_id: str, run_id: int, on_checkpoint: Callable[[dict, str], None] | None = None) -> None:
        """Tie the run to its row: files go to the project's workspace, checkpoints to `on_checkpoint`."""
        self.project_id, self.run_id = project_id, run_id
        self.workspace = workspace.root(project_id)
        self.on_checkpoint = on_checkpoint

    # ─── Control (any thread) ────────────────────────────────

    def stop(self) -> None:
        self.cancel.set()

    def say(self, content: str) -> None:
        """A note from the user. Every later turn sees all notes so far."""
        with self._lock:
            self._notes.append(content)
        self.bus.publish(AgentMessage(agent_name="You", content=content, message_type="user"))

    def decide(self, action: str, model: str | None = None, message: str | None = None) -> str | None:
        """Answer the pending decision. Returns an error message, or None if accepted."""
        with self._lock:
            pending = self._pending
            if not pending:
                return "No decision is pending"
            if action not in pending["options"]:
                return f"Choose one of: {', '.join(pending['options'])}"
            if action == "switch":
                if not model:
                    return "Pick a model to switch to"
                problem = self.model_problem(model)
                if problem:
                    return problem
            if action == "revise" and not (message and message.strip()):
                return "Say what to change in the plan"
            self._pending = None
        self._decisions.put({"action": action, "model": model, "message": message})
        return None

    def model_problem(self, ref: str) -> str | None:
        """Why a model can't be used in this run, or None."""
        try:
            provider, _ = providers.split_ref(ref)
        except ValueError as e:
            return str(e)
        if providers.provider_info(provider, self.endpoints) is None:
            return f"Unknown provider '{provider}'"
        if self.privacy and not providers.is_local(ref, self.endpoints):
            return f"Privacy Mode is on: {ref} is a cloud model"
        return None

    # ─── Pipeline ────────────────────────────────────────────

    def execute(self) -> RunResult:
        status = "complete"
        try:
            # Preflight speaks even when resuming; the replayed steps stay quiet.
            replay, self._replay = self._replay, []
            if self.resumed:
                self.publish("System", f"Resuming from the checkpoint: {len(replay)} step(s) already done.", "system")
            self._preflight()
            self._replay = replay
            self._pipeline()
        except Stopped as e:
            status = "stopped"
            self.publish("System", f"Run stopped: {e}.", "system")
        except Exception as e:
            log.exception("Run failed")
            status = "error"
            self.publish("System", f"Error: {providers.redact(str(e))}", "error")
        finally:
            self._close_mcp()
        return RunResult(status, self.tokens_in, self.tokens_out, round(self.cost_usd, 6))

    def _preflight(self) -> None:
        if self.mode in ("full", "code") and not self.steps["coder"]:
            raise RuntimeError("No agent has the coder role")
        if self.mode == "review":
            if not self.steps["reviewer"]:
                raise RuntimeError("No agent has the reviewer role")
            if not self.review_source:
                raise RuntimeError("Nothing to review yet: run a task in this project first")
        for agent in self.agents:
            problem = self.model_problem(agent.model)
            if problem:
                raise RuntimeError(f"{agent.name}: {problem}")
            self.warn_unpriced(agent)
        names = ", ".join(f"{a.name} ({a.model})" for a in self.agents)
        self.publish("System", f"Crew for this {self.mode} run: {names}", "system")
        for notice in self.notices:
            self.warn(notice, notice)

    def _pipeline(self) -> None:
        step = self.steps
        if self.mode == "review":
            self._turn(step["reviewer"][0], _brief(("Focus", self.prompt), ("Code to review", self.review_source)))
            return

        plan = ""
        if step["planner"]:
            plan = self._turn(step["planner"][0], _brief(("Task", self.prompt)))
            plan = self._discuss(plan)
            if self.approve_plan:
                plan = self._approve_plan(plan)
        if self.mode == "plan":
            for agent in step["docs"][:1]:
                self._turn(agent, _brief(("Task", self.prompt), ("Plan", plan)))
            return

        code = self._code_and_review(plan)
        if self.mode == "code":
            return

        extras = []
        for agent in step["custom"]:
            extras.append((agent.name, self._turn(agent, _brief(("Task", self.prompt), ("Plan", plan), ("Code", code)))))
        tests = ""
        for agent in step["tester"][:1]:
            tests = self._turn(agent, _brief(("Task", self.prompt), ("Code", code)))
            tests = self._build(agent, tests, ("Code", code), ("Tests", tests))
        for agent in step["docs"][:1]:
            self._turn(agent, _brief(("Task", self.prompt), ("Plan", plan), ("Code", code), ("Tests", tests), *extras))

    def _code_and_review(self, plan: str) -> str:
        coder = self.steps["coder"][0]
        reviewer = self.steps["reviewer"][0] if self.steps["reviewer"] else None
        code = feedback = ""
        for cycle in range(1, self.max_cycles + 1):
            code = self._turn(
                coder,
                _brief(
                    ("Task", self.prompt),
                    ("Plan", plan),
                    ("Your previous code", code if feedback else ""),
                    ("Review feedback to address", feedback),
                ),
            )
            code = self._build(coder, code, ("Your code", code))
            if reviewer is None:
                break
            review = self._turn(reviewer, _brief(("Task", self.prompt), ("Plan", plan), ("Code to review", code)))
            if verdict(review) == "APPROVED":
                break
            feedback = review
            if cycle == self.max_cycles:
                self.publish(
                    "System",
                    f"No approval after {self.max_cycles} review cycles; continuing with the latest code.",
                    "warning",
                )
        return code

    def _discuss(self, plan: str) -> str:
        """The optional crew discussion: coder and reviewer give feedback on the
        plan, the planner revises, until they agree or the rounds run out."""
        planner = self.steps["planner"][0]
        crew = [a for role in ("coder", "reviewer") for a in self.steps.get(role, [])[:1]]
        if not self.discussion_rounds or not crew:
            return plan
        for round_no in range(1, self.discussion_rounds + 1):
            feedback: list[tuple[str, str]] = []
            for agent in crew:
                brief = _brief(("Task", self.prompt), ("Plan", plan), ("Feedback so far this round", _transcript(feedback)))
                feedback.append((agent.name, self._turn(agent, brief, protocol="discuss")))
            if all(plan_agreed(reply) for _, reply in feedback):
                self.publish("System", f"The crew agreed on the plan after {round_no} round(s).", "system")
                return plan
            plan = self._revise(planner, plan, _transcript(feedback))
        self.publish("System", f"Discussion ended after {self.discussion_rounds} round(s); coding from the latest plan.", "system")
        return plan

    def _revise(self, planner: Agent, plan: str, feedback: str) -> str:
        return self._turn(planner, _brief(("Task", self.prompt), ("Your plan", plan), ("Feedback", feedback)), protocol="revise")

    def _approve_plan(self, plan: str) -> str:
        """Pause until the user approves the plan, sends changes (the planner
        revises and asks again), or stops."""
        while True:
            choice = self._ask(
                "The plan is ready. Approve it, describe changes for the planner, or stop.",
                {"kind": "plan_approval"},
                ["approve", "revise", "stop"],
            )
            if choice["action"] == "approve":
                return plan
            if choice["action"] != "revise":
                raise Stopped("the plan was not approved")
            self.publish("You", choice["message"], "user")
            plan = self._revise(self.steps["planner"][0], plan, f"### The user\n\n{choice['message']}")

    # ─── Turns ───────────────────────────────────────────────

    def _turn(self, agent: Agent, brief: str, protocol: str | None = None) -> str:
        """One agent turn. `protocol` picks reply instructions (and tools) other than the role's own."""
        step = protocol or agent.role
        if not self._next_step("reply", agent.name):
            done = self._replayed("turn", agent.name)
            if done is not None:
                agent.model = done["model"]  # the model it ended on, after any switch
                return done["text"]
        offered = self._tools_for(agent, step)
        instructions = "\n\n".join(filter(None, (roles.PROTOCOL.get(step), tools.PROTOCOL if offered else "")))
        system = agent.prompt + (f"\n\n{instructions}" if instructions else "")
        with self._lock:
            notes = list(self._notes)
        if notes:
            brief += "\n\n" + _brief(("Notes from the user (these take priority)", "\n\n".join(notes)))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": brief}]
        activity = roles.ACTIVITIES.get(step, "working")
        text = self._loop(agent, messages, offered, activity)
        if text is None:  # replaying: the turn had finished, and its result is the next saved step
            done = self._replayed("turn", agent.name)
            if done is None:
                raise RuntimeError("The checkpoint ends inside a turn")
            agent.model = done["model"]
            return done["text"]
        if step in WRITES_FILES:
            self._write_files(agent, text)
        self._steps.append({"kind": "turn", "agent": agent.name, "model": agent.model, "text": text})
        self._save()
        return text

    def _turn_start(self, agent: Agent, activity: str) -> None:
        """Who is working now, before any text arrives (thinking models start silent)."""
        self.publish(
            agent.name,
            f"{agent.name} is {activity}…",
            "turn_start",
            model=agent.model,
            data={"role": agent.role, "activity": activity},
        )

    def _loop(self, agent: Agent, messages: list[dict], offered: list[dict], activity: str) -> str | None:
        """Model calls and tool calls until the agent answers without tools. Returns
        the text of every reply, or None when replay reaches the turn's saved result."""
        limit = agent.max_tool_rounds or self.tool_rounds
        allowed = {t["name"] for t in offered}
        seen: Counter = Counter()
        texts: list[str] = []
        self._turn_start(agent, activity)
        for round_no in range(limit + 1):
            last = round_no == limit
            if last and offered:
                self.warn(f"rounds:{agent.name}", f"{agent.name} used all {limit} tool rounds in a turn and was asked to finish.")
                messages.append(
                    {"role": "user", "content": f"You've used all {limit} tool rounds for this turn. Give your final answer now."}
                )
            reply = self._model(agent, messages, offered, activity)
            if reply is None:
                return None
            if reply.text.strip():
                texts.append(reply.text)
            if not reply.tool_calls or last:
                break
            messages.append(harness.assistant_message(reply))
            for i, call in enumerate(reply.tool_calls):
                if i < MAX_TOOL_CALLS_PER_REPLY:
                    result = self._tool(agent, call, allowed, seen, activity)
                else:
                    result = ToolResult(f"Not run: at most {MAX_TOOL_CALLS_PER_REPLY} tool calls per reply.", "error")
                messages.append(harness.tool_message(call, result))
        return "\n\n".join(texts)

    def _model(self, agent: Agent, messages: list[dict], offered: list[dict], activity: str) -> harness.Reply | None:
        """One model call of the loop, or its saved reply when resuming. A key
        problem pauses for a model switch, then the call is made again."""
        if self._next_step("turn", agent.name):
            return None
        done = self._replayed("reply", agent.name)
        if done is not None:
            agent.model = done["model"]
            return harness.Reply(done["text"], [providers.ToolCall(**c) for c in done["tool_calls"]])
        while True:
            try:
                reply = self._call(agent, messages, offered)
                break
            except providers.ProviderError as e:
                if not (e.problem and e.problem.kind in providers.PAUSING):
                    raise
                self._replace_model(agent, e)
                self._turn_start(agent, activity)
        if reply.tool_calls:
            calls = [asdict(c) for c in reply.tool_calls]
            self._steps.append({"kind": "reply", "agent": agent.name, "model": agent.model, "text": reply.text, "tool_calls": calls})
            self._save()
        return reply

    # ─── Tools ───────────────────────────────────────────────

    def _tools_for(self, agent: Agent, step: str) -> list[dict]:
        """The tool schemas this turn offers: the step's built-in tools and the MCP
        servers' tools for the agent's role. None without a workspace, or for a
        model known to refuse tools."""
        if self.project_id is None or not providers.supports_tools(agent.model):
            return []
        names = [n for n in tools.ROLE_TOOLS.get(step, ()) if n != "handoff" or self._can_hand_off(agent)]
        offered = [tools.BUILTIN[n].schema() for n in names]
        for tool in self._mcp_tools_for(agent):
            offered.append(tool.schema())
        return offered

    def _can_hand_off(self, agent: Agent) -> bool:
        return self.max_handoffs > 0 and any(a is not agent for a in self.agents)

    def _tool(self, agent: Agent, call: providers.ToolCall, allowed: set[str], seen: Counter, activity: str) -> ToolResult:
        try:
            args = json.loads(call.arguments or "{}")
        except ValueError:
            args = None
        if not isinstance(args, dict):
            return ToolResult("The arguments weren't a JSON object.", "error")
        ctx = harness.ToolContext(self, agent, call, args, allowed, seen, activity)
        return harness.chain(self.tool_middleware, self._run_tool)(ctx)

    def _run_tool(self, ctx: harness.ToolContext) -> ToolResult:
        """The innermost tool step. Finished tools replay from the checkpoint;
        commands and handoffs replay through their own steps."""
        name = ctx.call.name
        mcp_tool = self._mcp_tools.get(name)
        schema = mcp_tool.parameters if mcp_tool else tools.BUILTIN[name].parameters
        problem = tools.check_args(schema, ctx.args)
        if problem:
            return ToolResult(f"Wrong arguments for {name}: {problem}.", "error")
        if name == "run_command":
            return self._tool_command(ctx)
        if name == "handoff":
            return self._handoff(ctx)
        done = self._replayed("tool", ctx.agent.name)
        if done is not None:
            return ToolResult(**done["result"])
        assert self.project_id is not None
        if mcp_tool is not None:
            result = self._mcp_call(ctx, mcp_tool)
        elif name == "write_file":
            result = self._tool_write(ctx)
        else:
            try:
                result = ToolResult(tools.run_read(self.project_id, name, ctx.args))
            except (ValueError, OSError) as e:  # ToolError and PathRefused are ValueErrors
                result = ToolResult(str(e) or "It couldn't be read.", "error")
        self._steps.append({"kind": "tool", "agent": ctx.agent.name, "tool": name, "result": asdict(result)})
        self._save()
        return result

    def _tool_write(self, ctx: harness.ToolContext) -> ToolResult:
        assert self.project_id is not None and self.run_id is not None
        path, content = ctx.args["path"], ctx.args["content"]
        try:
            written, refused = workspace.write_files(self.project_id, self.run_id, [(path, content)])
        except OSError as e:
            return ToolResult(f"{path} couldn't be written: {e.strerror or e}", "error")
        if not written:
            return ToolResult(f"{path} wasn't written: {refused[0][1]}.", "error")
        self.publish(ctx.agent.name, f"{ctx.agent.name} wrote {written[0]}", "files", data={"paths": written})
        return ToolResult(f"Wrote {written[0]} ({len(content):,} characters).")

    def _tool_command(self, ctx: harness.ToolContext) -> ToolResult:
        if self.workspace is None:
            return ToolResult("There's no project folder to run commands in.", "error")
        result = self._command(ctx.agent.name, ctx.args["command"])
        status = {"denied": "denied", "error": "error"}.get(result.status, "ok")
        return ToolResult(_command_report(result), status)

    def _colleague(self, wanted: str) -> Agent | None:
        """A crew member by name, or else the first one with that role."""
        key = wanted.strip().lower()
        by_name = next((a for a in self.agents if a.name.lower() == key), None)
        return by_name or next((a for a in self.agents if a.role == key), None)

    def _handoff(self, ctx: harness.ToolContext) -> ToolResult:
        """The colleague takes a turn on the caller's reason; its reply is the result.
        Limits: no handoff to yourself or to anyone waiting on one, at most
        max_handoffs per run, and at most max_cycles between any two agents."""
        caller, wanted, reason = ctx.agent, ctx.args["to"], ctx.args["reason"]
        target = self._colleague(wanted)
        if target is None:
            names = ", ".join(f"{a.name} ({a.role})" for a in self.agents if a is not caller)
            return ToolResult(f"No one called '{wanted}' is in this crew. Colleagues: {names}.", "error")
        if target is caller:
            return ToolResult("You can't hand off to yourself.", "error")
        if target.name in self._waiting:
            return ToolResult(f"{target.name} is waiting for your reply to their handoff. Finish your part and reply instead.", "error")
        if self.handoffs >= self.max_handoffs:
            return ToolResult(f"The handoff limit for this run ({self.max_handoffs}) is reached. Complete your step yourself.", "error")
        pair = frozenset((caller.name, target.name))
        if self._pairs[pair] >= self.max_cycles:
            return ToolResult(
                f"You and {target.name} have handed work to each other {self.max_cycles} times already. Complete your step yourself.",
                "error",
            )
        self.handoffs += 1
        self._pairs[pair] += 1
        self.publish(
            "System", f"{caller.name} hands off to {target.name}: {reason}", "system", data={"from": caller.name, "to": target.name}
        )
        self._waiting.append(caller.name)
        try:
            reply = self._turn(target, _brief(("Task", self.prompt), (f"Handoff from {caller.name}", reason)))
        finally:
            self._waiting.pop()
        self._turn_start(caller, ctx.activity)
        return ToolResult(reply.strip() or f"{target.name} replied with nothing.")

    # ─── MCP ─────────────────────────────────────────────────

    def _mcp_tools_for(self, agent: Agent) -> list[mcp.McpTool]:
        if not self.mcp_servers:
            return []
        if self._mcp is None:
            self._start_mcp()
        assert self._mcp is not None
        return [t for t in self._mcp_tools.values() if agent.role in (self._mcp[t.server].cfg.get("roles") or roles.ROLES)]

    def _start_mcp(self) -> None:
        """Start the enabled MCP servers this run may use, once, and list their tools."""
        self._mcp = {}
        needs_sandbox = any(c.get("transport") != "http" and c.get("sandbox") for c in self.mcp_servers.values())
        off = self._sandbox_state() if needs_sandbox else None
        for name, cfg in self.mcp_servers.items():
            problem = mcp.start_problem(cfg, privacy=self.privacy, sandbox_off=off)
            if problem:
                self.warn(f"mcp:{name}", f"The MCP server {name} isn't used in this run: {problem}.")
                continue
            server = mcp.Server(name, cfg)
            try:
                if self.project_id is not None:  # its working folder, and the sandbox mount
                    workspace.ensure(self.project_id)
                found = server.start(self.workspace, self.sandbox)
            except (mcp.McpError, ValueError) as e:
                if server.sandboxed and "No such image" in str(e):
                    self._no_image()
                self.warn(f"mcp:{name}", f"The MCP server {name} didn't start: {e}.")
                continue
            self._mcp[name] = server
            for tool in found:
                self._mcp_tools.setdefault(tool.full_name, tool)
        if self._mcp_tools:
            self.publish("System", f"MCP tools for this run: {', '.join(sorted(self._mcp_tools))}", "system")

    def _mcp_call(self, ctx: harness.ToolContext, tool: mcp.McpTool) -> ToolResult:
        """Call an MCP tool, asking first unless the user trusts it and its server can't reach this machine's files."""
        assert self._mcp is not None
        server = self._mcp[tool.server]
        contained = server.sandboxed or server.cfg.get("transport") == "http"
        if not (tool.name in server.trusted and contained):
            reason = (
                "its server runs on this machine, outside the sandbox"
                if not contained
                else "MCP tools ask first unless you trust them in Settings"
            )
            shown = json.dumps(ctx.args, indent=2, ensure_ascii=False)
            choice = self._ask(
                f"{ctx.agent.name} wants to use {tool.name} from the MCP server {server.name} ({reason}). Approve or deny it.\n\n{shown[:4000]}",
                {
                    "kind": "tool_approval",
                    "agent": ctx.agent.name,
                    "tool": tool.name,
                    "server": server.name,
                    "args": ctx.args,
                    "sandbox": server.sandboxed,
                    "reason": reason,
                },
                ["approve", "deny"],
                record=False,  # the tool step records the outcome
            )
            if choice["action"] != "approve":
                return ToolResult("The user denied this call.", "denied", server.name)
        try:
            text, failed = server.call(tool.name, ctx.args, self.cancel)
        except mcp.McpError as e:
            if self.cancel.is_set():
                raise Stopped("stopped by the user") from None
            return ToolResult(f"The MCP server {server.name} failed: {e}", "error", server.name)
        return ToolResult(tools.cut(text), "error" if failed else "ok", server.name)

    def _close_mcp(self) -> None:
        for server in (self._mcp or {}).values():
            server.close()
        self._mcp = None
        self._mcp_tools = {}

    # ─── Workspace and commands ──────────────────────────────

    def _write_files(self, agent: Agent, text: str) -> None:
        """Write the turn's path-labelled blocks to the workspace."""
        if self.project_id is None or self.run_id is None:
            return
        files = workspace.extract_files(text)
        if not files:
            return
        try:
            written, refused = workspace.write_files(self.project_id, self.run_id, files)
        except OSError as e:
            self.publish("System", f"{agent.name}'s files couldn't be written: {e.strerror or e}", "error")
            return
        if written:
            self.publish(
                agent.name,
                f"{agent.name} wrote {len(written)} file(s): {', '.join(written)}",
                "files",
                data={"paths": written},
            )
        for rel, why in refused:
            self.publish("System", f"Skipped {rel[:120]!r} from {agent.name}: {why}.", "warning")

    def _build(self, agent: Agent, text: str, *context: tuple[str, str]) -> str:
        """Run the commands a turn proposed. If any fails, the coder gets one fix
        pass and the failed commands run once more. Returns the text plus the fix."""
        if self.workspace is None:
            return text
        commands = workspace.extract_commands(text)
        if len(commands) > MAX_COMMANDS_PER_TURN:
            self.publish(
                "System", f"{agent.name} proposed {len(commands)} commands; only the first {MAX_COMMANDS_PER_TURN} run.", "warning"
            )
        results = [self._command(agent.name, c) for c in commands[:MAX_COMMANDS_PER_TURN]]
        failed = [r for r in results if r.status in ("failed", "timeout")]
        coder = self.steps["coder"][0] if self.steps.get("coder") else None
        if not failed or coder is None:
            return text
        report = "\n\n".join(_command_report(r) for r in failed)
        fix = self._turn(coder, _brief(("Task", self.prompt), *context, ("Failed commands", report)), protocol="fix")
        for r in failed:
            self._command(coder.name, r.command)
        return f"{text}\n\n{fix}"

    def _sandbox_state(self) -> str | None:
        """Why the sandbox is off for this run, or None if it's on. Checked once per run."""
        if not self._sandbox_checked:
            self._sandbox_checked = True
            self._sandbox_off = terminal.sandbox_problem(self.sandbox)
            if self._sandbox_off and self.sandbox.get("enabled"):
                self.warn("sandbox", f"Agent commands will ask first: {self._sandbox_off}.")
        return self._sandbox_off

    def _command(self, agent_name: str, command: str) -> terminal.CommandResult:
        """Run one agent command, asking first unless it may run on its own."""
        done = self._replayed("command")
        if done is not None:
            return terminal.CommandResult(**done["result"])
        assert self.project_id is not None and self.workspace is not None
        if len(command) > terminal.MAX_COMMAND_CHARS:
            self.publish("System", f"Skipped a command from {agent_name}: it's over {terminal.MAX_COMMAND_CHARS} characters.", "warning")
            return self._log_command(terminal.CommandResult(command[:200], "denied"))
        off = self._sandbox_state()
        reason = terminal.approval_reason(command, off)
        if reason:
            where = "in the Docker sandbox" if off is None else "on this machine, outside any sandbox"
            choice = self._ask(
                f"{agent_name} wants to run this command {where} ({reason}). Approve or deny it.\n\n{command}",
                {"kind": "command_approval", "agent": agent_name, "command": command, "sandbox": off is None, "reason": reason},
                ["approve", "deny"],
                record=False,  # the command step records the answer
            )
            if choice["action"] != "approve":
                result = terminal.CommandResult(command, "denied", sandbox=off is None)
                self.publish(agent_name, _command_report(result), "command", data=asdict(result))
                return self._log_command(result)

        workspace.ensure(self.project_id)
        self.publish(agent_name, command, "command_start", data={"command": command, "sandbox": off is None})
        try:
            result = terminal.run_command(
                command,
                self.workspace,
                self.sandbox,
                sandboxed=off is None,
                direct=reason is None,
                cancel=self.cancel,
                on_output=lambda text: self.publish(agent_name, text, "command_output", data={"command": command}),
            )
        except ValueError as e:
            result = terminal.CommandResult(command, "error", output=str(e), sandbox=off is None)
        if result.status == "stopped":
            raise Stopped("stopped by the user")
        self.publish(agent_name, _command_report(result), "command", data=asdict(result))
        if result.status == "error" and result.sandbox and result.exit_code in (126, 127):
            self.warn(
                f"image:{command.split()[0]}",
                f"'{command.split()[0]}' isn't in the sandbox image {self.sandbox['image']}. Pick an image that has it.",
            )
        elif result.status == "error" and result.sandbox and "No such image" in result.output:
            self._no_image()
        return self._log_command(result)

    def _no_image(self) -> None:
        image = self.sandbox["image"]
        self.warn(
            f"no-image:{image}",
            f"The sandbox image {image} isn't on this machine, and JULI doesn't download images. "
            f"Run `docker pull {image}`, or pick an image you have in Settings > Sandbox.",
        )

    def _log_command(self, result: terminal.CommandResult) -> terminal.CommandResult:
        self._steps.append({"kind": "command", "result": asdict(result)})
        self._save()
        return result

    def _call(self, agent: Agent, messages: list[dict], offered: list[dict] | None = None) -> harness.Reply:
        """One model call through the model middleware."""
        call = harness.ModelCall(self, agent, messages, offered or [], harness.estimate(messages))
        return harness.chain(self.model_middleware, self._stream)(call)

    def _stream(self, call: harness.ModelCall) -> harness.Reply:
        """The innermost step: stream the reply, publishing chunks, until it ends,
        Stop is pressed or a cap would be passed."""
        agent = call.agent
        reply = harness.Reply()
        parts: list[str] = []
        out_chars = 0
        chunks = providers.stream(
            agent.model,
            list(call.messages),
            privacy=self.privacy,
            max_tokens=agent.max_tokens,
            num_ctx=agent.num_ctx,
            cancel=self.cancel,
            endpoints=self.endpoints,
            tools=call.tools or None,
        )
        try:
            for item in chunks:
                if isinstance(item, providers.Usage):
                    reply.usage = item
                    continue
                if isinstance(item, providers.ToolCall):
                    reply.tool_calls.append(item)
                    out_chars += len(item.arguments)
                else:
                    parts.append(item)
                    out_chars += len(item)
                    self.publish(agent.name, item, "chunk", model=agent.model)
                if self.cancel.is_set():
                    break
                reply.cut = self.cap_hit(agent.model, call.est_in, harness.estimate_tokens(out_chars))
                if reply.cut:
                    break
        finally:
            chunks.close()
        reply.text = "".join(parts)
        if call.tools and not providers.supports_tools(agent.model):
            self.warn(f"tools:{agent.model}", f"{agent.model} doesn't take tool calls, so it uses file and command blocks instead.")
        return reply

    def cap_hit(self, model: str, tokens_in: int, tokens_out: int) -> str | None:
        """The cap this call would exceed, if any."""
        if self.token_cap and self.tokens_in + self.tokens_out + tokens_in + tokens_out > self.token_cap:
            return "token_cap"
        if self.budget:
            call_cost = providers.cost(model, tokens_in, tokens_out, self.endpoints)
            if call_cost is not None and self.cost_usd + call_cost > self.budget:
                return "budget"
        return None

    def warn_unpriced(self, agent: Agent) -> None:
        """The budget cap counts cost, so it can't limit a cloud model whose price isn't known."""
        if self.budget and providers.cost(agent.model, 0, 0, self.endpoints) is None:
            self.warn(
                f"price:{agent.model}",
                f"{agent.model} has no known price, so the budget cap can't count its cost. Set a token cap to limit it.",
            )

    def limit_reached(self, cap: str) -> None:
        label = f"budget cap of ${self.budget:.2f}" if cap == "budget" else f"token cap of {self.token_cap:,} tokens"
        limit = self.budget if cap == "budget" else self.token_cap
        self.publish(
            "System",
            f"Limit reached: the {label}. The run stops here and keeps its output so far.",
            "limit_reached",
            data={"cap": cap, "limit": limit},
        )
        raise Stopped(f"the {label} was reached")

    def record_usage(self, agent: Agent, text: str, usage: providers.Usage) -> None:
        self.tokens_in += usage.tokens_in
        self.tokens_out += usage.tokens_out
        self.cost_usd += usage.cost_usd or 0.0
        self.publish(
            agent.name,
            text,
            "agent",
            model=agent.model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost_usd=usage.cost_usd,
        )
        provider = agent.model.partition(":")[0]
        for warning in usage.warnings:
            self.warn(f"low:{provider}:{warning.split(':')[0]}", f"{provider} rate limit running low: {warning}")
        self._check_allowance(provider)

    def _check_allowance(self, provider: str) -> None:
        allowance = self.allowances.get(provider)
        if not allowance:
            return
        spent = store.spend_since(provider, month_start())
        line = f"{provider} has used ${spent:.2f} of its ${allowance:.2f} monthly allowance"
        if spent >= allowance:
            self.warn(f"allowance100:{provider}", f"{line}. New runs with it are blocked until next month.")
        elif spent >= 0.8 * allowance:
            self.warn(f"allowance80:{provider}", line)

    # ─── Pauses ──────────────────────────────────────────────

    def _replace_model(self, agent: Agent, error: providers.ProviderError) -> None:
        problem = error.problem
        assert problem is not None
        reason = f"{agent.name} can't continue on {agent.model}: {problem.message}."
        if self.fallback and self.fallback != agent.model and providers.is_local(self.fallback, self.endpoints):
            self.publish("System", f"{reason} Switching {agent.name} to {self.fallback}.", "warning")
            agent.model = self.fallback
            return
        choice = self._ask(
            f"{reason} Switch to another model and resume, or stop.",
            {"kind": "key_problem", "agent": agent.name, "model": agent.model, "problem": problem.kind},
            ["switch", "stop"],
            record=False,  # the turn step records the model it ended on
        )
        if choice["action"] != "switch":
            raise Stopped("stopped at the paused decision")
        agent.model = choice["model"]
        self.publish("System", f"Resuming: {agent.name} now uses {agent.model}.", "system")

    def _ask(self, content: str, data: dict, options: list[str], record: bool = True) -> dict:
        """Pause until decide() answers (or the run is stopped). With `record`,
        the answer is a checkpoint step of its own."""
        if record:
            done = self._replayed("decision")
            if done is not None:
                return done["choice"]
        with self._lock:
            self._pending = {"options": options}
            while not self._decisions.empty():
                self._decisions.get_nowait()
        self.bus.set_task_status("paused")
        self.publish("System", content, "decision", data={**data, "options": options})
        self._save("paused")
        try:
            while True:
                if self.cancel.is_set():
                    raise Stopped("stopped by the user")
                try:
                    choice = self._decisions.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.bus.set_task_status("running")
                break
        finally:
            with self._lock:
                self._pending = None
        if record:
            self._steps.append({"kind": "decision", "choice": choice})
        self._save()
        return choice

    # ─── Checkpoints ─────────────────────────────────────────

    def checkpoint(self) -> dict:
        """Everything needed to rebuild this run and replay its steps so far."""
        with self._lock:
            notes = list(self._notes)
        return {
            "version": CHECKPOINT_VERSION,
            "prompt": self.prompt,
            "mode": self.mode,
            "crew": [asdict(a) for a in self.crew],
            "options": {
                "max_cycles": self.max_cycles,
                "approve_plan": self.approve_plan,
                "discussion_rounds": self.discussion_rounds,
                "no_devops": self.no_devops,
            },
            "review_source": self.review_source,
            "notes": notes,
            "steps": list(self._steps),
            "usage": {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "cost_usd": self.cost_usd},
        }

    @classmethod
    def from_checkpoint(cls, state: dict, *, settings: dict, notices: list[str] | None = None, bus: MessageBus = message_bus) -> "Run":
        """Rebuild a run from its checkpoint. Limits, Privacy Mode and endpoints
        come from today's settings; the crew is the one the run started with."""
        if state.get("version") != CHECKPOINT_VERSION:
            raise ValueError("This checkpoint was saved by another version of JULI")
        names = {f.name for f in fields(Agent)}
        crew = [Agent(**{k: v for k, v in a.items() if k in names}) for a in state["crew"]]
        options = {
            k: v for k, v in (state.get("options") or {}).items() if k in ("max_cycles", "approve_plan", "discussion_rounds", "no_devops")
        }
        run = cls(
            state["prompt"],
            state["mode"],
            crew,
            settings=settings,
            review_source=state.get("review_source") or "",
            notices=notices or (),
            bus=bus,
            **options,
        )
        run._replay = list(state.get("steps") or [])
        run._notes = list(state.get("notes") or [])
        usage = state.get("usage") or {}
        run.tokens_in, run.tokens_out = int(usage.get("tokens_in") or 0), int(usage.get("tokens_out") or 0)
        run.cost_usd = float(usage.get("cost_usd") or 0.0)
        run.resumed = True
        return run

    def _save(self, status: str = "running") -> None:
        if self.on_checkpoint is None:
            return
        try:
            self.on_checkpoint(self.checkpoint(), status)
        except Exception:
            log.exception("Could not save the run's checkpoint")

    @property
    def replaying(self) -> bool:
        return bool(self._replay)

    def _next_step(self, kind: str, agent: str) -> bool:
        """Whether the next saved step (when resuming) is this kind of step by this agent."""
        return bool(self._replay) and self._replay[0].get("kind") == kind and self._replay[0].get("agent") == agent

    def _replayed(self, kind: str, agent: str | None = None) -> dict | None:
        """The next saved step, when resuming and it is this kind of step."""
        if not self._replay:
            return None
        step = self._replay[0]
        if step.get("kind") != kind or (agent is not None and step.get("agent") != agent):
            self._replay.clear()
            self.publish("System", "The checkpoint doesn't match this run's next step; continuing live from here.", "warning")
            return None
        self._steps.append(self._replay.pop(0))
        return step

    # ─── Events ──────────────────────────────────────────────

    def publish(self, agent_name: str, content: str, message_type: str, **fields) -> None:
        if self._replay:
            return  # replaying a checkpoint: these messages went out the first time
        self.bus.publish(AgentMessage(agent_name=agent_name, content=content, message_type=message_type, **fields))

    def warn(self, key: str, content: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self.publish("System", content, "warning")


# ─── The active run ──────────────────────────────────────────

_active: Run | None = None
_active_lock = threading.Lock()


def begin(project_id: str, run: Run, run_id: int | None = None) -> int | None:
    """Claim the bus for a run and create its run row (or reopen `run_id` to
    resume it). None if a task is already running."""
    if not run.bus.try_begin_task(run.prompt, project_id):
        return None
    try:
        if run_id is None:
            crew_json = json.dumps([a.summary() for a in run.agents])
            run_id = store.create_run(project_id, run.prompt, run.mode, crew_json)
        else:
            store.reopen_run(run_id)
    except Exception:
        run.bus.set_task_status("error")
        raise
    row_id = run_id
    run.bus.start_run(project_id, row_id)
    run.attach(project_id, row_id, lambda state, status: store.save_checkpoint(row_id, json.dumps(state), status))
    run._save()  # a crash in the first turn can resume too
    return row_id


def execute(run: Run) -> RunResult:
    """Run to the end as the active run, then publish the final status."""
    global _active
    with _active_lock:
        _active = run
    try:
        result = run.execute()
    finally:
        with _active_lock:
            if _active is run:
                _active = None
    run.bus.set_task_status(result.status)
    return result


def stop() -> bool:
    with _active_lock:
        run = _active
    if run is None:
        return False
    run.stop()
    return True


def decide(action: str, model: str | None = None, message: str | None = None) -> str | None:
    with _active_lock:
        run = _active
    if run is None:
        return "No task is running"
    return run.decide(action, model, message)


def say(content: str) -> bool:
    """Pass a user note to the running task. False if none is running."""
    with _active_lock:
        run = _active
    if run is None:
        return False
    run.say(content)
    return True


# ─── Follow-up chat ──────────────────────────────────────────


def follow_up(run_row: dict, agent_name: str, question: str, settings: dict) -> dict:
    """Ask one agent about a finished run, with its output and earlier
    follow-ups as context. The question and answer are stored with the run.

    A follow-up is a small run of its own: its model calls pass the same
    middleware as a run's (Privacy Mode, the token and budget caps, usage),
    and the caps count this one answer. A cap that would be passed before
    anything is sent raises Stopped; one that cuts the answer short keeps
    what there is, with a notice. What a run would warn about (a model the
    budget cap can't count, an allowance or rate limit running low) comes
    back as warnings."""
    agent = next(a for a in build_crew(settings) if a.name == agent_name)
    history = store.run_messages(run_row["id"])
    output = _transcript([(m["agent_name"], m["content"]) for m in history if m["message_type"] == "agent"])

    turns: list[dict] = []
    for m in history:
        if m["message_type"] not in ("question", "answer"):
            continue
        if m["message_type"] == "answer" and not m["content"].strip():
            continue  # a cap cut it short before any text
        role = "user" if m["message_type"] == "question" else "assistant"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + m["content"]
        else:
            turns.append({"role": role, "content": m["content"]})
    if turns and turns[-1]["role"] == "user":
        turns[-1]["content"] += "\n\n" + question
    else:
        turns.append({"role": "user", "content": question})
    turns[0]["content"] = _brief(("Task", run_row["prompt"]), ("Run output", output), ("Question", turns[0]["content"]))
    offered = [tools.BUILTIN[n].schema() for n in tools.ROLE_TOOLS["follow_up"]] if providers.supports_tools(agent.model) else []
    system = agent.prompt + "\n\n" + roles.PROTOCOL["follow_up"] + (f"\n\n{tools.PROTOCOL}" if offered else "")
    messages = [{"role": "system", "content": system}, *turns]
    limit = agent.max_tool_rounds or int(settings["run"].get("max_tool_rounds") or config.DEFAULT_RUN["max_tool_rounds"])

    # The one agent as a run on a bus of its own: nothing is broadcast, and the
    # bus keeps what each call recorded (its text, tokens and cost) and any warnings.
    asking = Run(question, "full", [agent], settings=settings, bus=MessageBus())
    asking.allowances = {}  # checked below instead, once this answer's cost is stored and counts
    asking.warn_unpriced(agent)
    notice: str | None = None
    try:
        for round_no in range(limit + 1):
            if round_no == limit and offered:
                messages.append(
                    {"role": "user", "content": f"You've used all {limit} tool rounds for this turn. Give your final answer now."}
                )
            reply = asking._call(agent, messages, offered)
            if not reply.tool_calls or round_no == limit:
                break
            messages.append(harness.assistant_message(reply))
            for i, call in enumerate(reply.tool_calls):
                if i < MAX_TOOL_CALLS_PER_REPLY:
                    result = _read_tool(run_row["project_id"], call)
                else:
                    result = ToolResult(f"Not run: at most {MAX_TOOL_CALLS_PER_REPLY} tool calls per reply.", "error")
                messages.append(harness.tool_message(call, result))
    except Stopped as e:
        if not (asking.tokens_in or asking.tokens_out):
            raise Stopped(f"The question wasn't sent: {e}. Raise the cap in Settings to ask it.") from None
        notice = f"The answer stops here: {e}."

    warnings = [m.content for m in asking.bus.history if m.message_type == "warning"]
    answers = [m for m in asking.bus.history if m.message_type == "agent"]
    reply_text = "\n\n".join(m.content for m in answers if m.content.strip())
    tokens_in = sum(m.tokens_in or 0 for m in answers)
    tokens_out = sum(m.tokens_out or 0 for m in answers)
    cost_usd: float | None = None
    if (tokens_in or tokens_out) and all(m.cost_usd is not None for m in answers):
        cost_usd = sum(m.cost_usd or 0.0 for m in answers)

    project_id, run_id = run_row["project_id"], run_row["id"]
    store.save_message(project_id, run_id, {"agent_name": "You", "content": question, "message_type": "question"})
    store.save_message(
        project_id,
        run_id,
        {
            "agent_name": agent.name,
            "content": reply_text,
            "message_type": "answer",
            "model": agent.model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
        },
    )
    near, used_up = allowance_report([agent], settings)
    warnings += near + [f"{line}. New runs with it are blocked until next month." for line in used_up]
    # Under the agent's own name, so they stay with its answer when the view shows only that agent.
    for warning in warnings:
        store.save_message(project_id, run_id, {"agent_name": agent.name, "content": warning, "message_type": "warning"})
    if notice:
        store.save_message(project_id, run_id, {"agent_name": agent.name, "content": notice, "message_type": "limit_reached"})
    return {
        "agent": agent.name,
        "reply": reply_text,
        "model": agent.model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "warnings": warnings,
        "notice": notice,  # a cap cut the answer short
    }


def _read_tool(project_id: str, call: providers.ToolCall) -> ToolResult:
    """A read-only tool for a follow-up answer (no run, so no events or checkpoints)."""
    if call.name not in tools.READ:
        return ToolResult(f"'{call.name}' can't be used in a follow-up.", "error")
    try:
        args = json.loads(call.arguments or "{}")
    except ValueError:
        args = None
    if not isinstance(args, dict):
        return ToolResult("The arguments weren't a JSON object.", "error")
    problem = tools.check_args(tools.BUILTIN[call.name].parameters, args)
    if problem:
        return ToolResult(f"Wrong arguments for {call.name}: {problem}.", "error")
    try:
        return ToolResult(tools.run_read(project_id, call.name, args))
    except (ValueError, OSError) as e:
        return ToolResult(str(e) or "It couldn't be read.", "error")
