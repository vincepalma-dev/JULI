"""
The lean engine: Plan -> Code<->Review -> custom roles -> Test -> Docs.

One agent turn is one streamed model call. While it streams, the turn
publishes chunk events; when it ends, one agent message with its model,
tokens and cost. The crew and the optional limits come from settings.

Optionally, the crew discusses the plan before coding, and the user can
send notes mid-run that every later agent sees. A run can pause for a
decision (plan approval, or a key that is missing, invalid or out of credit)
and can be stopped at any time. The API reaches the active run through
stop(), decide() and say(). follow_up() answers questions about a finished run.
"""

import json
import logging
import math
import queue
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from juli import providers, roles, store
from juli.bus import AgentMessage, MessageBus, message_bus

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


@dataclass
class Agent:
    name: str
    role: str
    model: str
    prompt: str
    max_tokens: int | None = None
    num_ctx: int | None = None

    def summary(self) -> dict:
        return {"name": self.name, "role": self.role, "model": self.model, "max_tokens": self.max_tokens}


@dataclass
class RunResult:
    status: str  # complete, stopped, error
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class Stopped(Exception):
    """The run ends early, keeping its partial output."""


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
    now = datetime.now(timezone.utc)
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
    """The latest run's output in a project, as text for the reviewer."""
    return "\n\n".join(f"### {m['agent_name']}\n\n{m['content']}" for m in store.latest_output(project_id))


def _tokens(chars: int) -> int:
    return math.ceil(chars / 4)


def _estimate(messages: list[dict]) -> int:
    return _tokens(sum(len(m["content"]) for m in messages))


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

        self.cancel = threading.Event()
        self.tokens_in = self.tokens_out = 0
        self.cost_usd = 0.0
        self._decisions: queue.Queue = queue.Queue()
        self._pending: dict | None = None
        self._lock = threading.Lock()
        self._warned: set[str] = set()
        self._notes: list[str] = []  # the user's mid-run messages

    # ─── Control (any thread) ────────────────────────────────

    def stop(self) -> None:
        self.cancel.set()

    def say(self, content: str) -> None:
        """A note from the user. Every later turn sees all notes so far."""
        with self._lock:
            self._notes.append(content)
        self._publish("You", content, "user")

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
            self._preflight()
            self._pipeline()
        except Stopped as e:
            status = "stopped"
            self._publish("System", f"Run stopped: {e}.", "system")
        except Exception as e:
            log.exception("Run failed")
            status = "error"
            self._publish("System", f"Error: {providers.redact(str(e))}", "error")
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
            if self.budget and providers.cost(agent.model, 0, 0, self.endpoints) is None:
                self._warn(
                    f"price:{agent.model}",
                    f"{agent.model} has no known price, so the budget cap can't count its cost. "
                    "Set a token cap to limit it.",
                )
        names = ", ".join(f"{a.name} ({a.model})" for a in self.agents)
        self._publish("System", f"Crew for this {self.mode} run: {names}", "system")
        for notice in self.notices:
            self._warn(notice, notice)

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
            if reviewer is None:
                break
            review = self._turn(reviewer, _brief(("Task", self.prompt), ("Plan", plan), ("Code to review", code)))
            if verdict(review) == "APPROVED":
                break
            feedback = review
            if cycle == self.max_cycles:
                self._publish(
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
                self._publish("System", f"The crew agreed on the plan after {round_no} round(s).", "system")
                return plan
            plan = self._revise(planner, plan, _transcript(feedback))
        self._publish("System", f"Discussion ended after {self.discussion_rounds} round(s); coding from the latest plan.", "system")
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
            self._publish("You", choice["message"], "user")
            plan = self._revise(self.steps["planner"][0], plan, f"### The user\n\n{choice['message']}")

    # ─── Turns ───────────────────────────────────────────────

    def _turn(self, agent: Agent, brief: str, protocol: str | None = None) -> str:
        """One agent turn. `protocol` picks reply instructions other than the role's own."""
        instructions = roles.PROTOCOL.get(protocol or agent.role)
        system = agent.prompt + (f"\n\n{instructions}" if instructions else "")
        with self._lock:
            notes = list(self._notes)
        if notes:
            brief += "\n\n" + _brief(("Notes from the user (these take priority)", "\n\n".join(notes)))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": brief}]
        while True:
            try:
                return self._call(agent, messages)
            except providers.ProviderError as e:
                if not (e.problem and e.problem.kind in providers.PAUSING):
                    raise
                self._replace_model(agent, e)

    def _call(self, agent: Agent, messages: list[dict]) -> str:
        if self.cancel.is_set():
            raise Stopped("stopped by the user")
        est_in = _estimate(messages)
        cap = self._cap_hit(agent.model, est_in, agent.max_tokens or 0)
        if cap:
            self._limit_reached(cap)

        parts: list[str] = []
        usage = None
        out_chars = 0
        chunks = providers.stream(
            agent.model,
            messages,
            privacy=self.privacy,
            max_tokens=agent.max_tokens,
            num_ctx=agent.num_ctx,
            cancel=self.cancel,
            endpoints=self.endpoints,
        )
        try:
            for item in chunks:
                if isinstance(item, providers.Usage):
                    usage = item
                    continue
                parts.append(item)
                out_chars += len(item)
                self._publish(agent.name, item, "chunk", model=agent.model)
                if self.cancel.is_set():
                    break
                cap = self._cap_hit(agent.model, est_in, _tokens(out_chars))
                if cap:
                    break
        finally:
            chunks.close()

        if usage is None and parts:  # cut short: estimate what was used
            tokens_out = _tokens(out_chars)
            usage = providers.Usage(est_in, tokens_out, providers.cost(agent.model, est_in, tokens_out, self.endpoints))
        text = "".join(parts)
        if usage is not None:
            self._record(agent, text, usage)
        if self.cancel.is_set():
            raise Stopped("stopped by the user")
        if cap:
            self._limit_reached(cap)
        return text

    def _cap_hit(self, model: str, tokens_in: int, tokens_out: int) -> str | None:
        """The cap this call would exceed, if any."""
        if self.token_cap and self.tokens_in + self.tokens_out + tokens_in + tokens_out > self.token_cap:
            return "token_cap"
        if self.budget:
            call_cost = providers.cost(model, tokens_in, tokens_out, self.endpoints)
            if call_cost is not None and self.cost_usd + call_cost > self.budget:
                return "budget"
        return None

    def _limit_reached(self, cap: str) -> None:
        label = f"budget cap of ${self.budget:.2f}" if cap == "budget" else f"token cap of {self.token_cap:,} tokens"
        limit = self.budget if cap == "budget" else self.token_cap
        self._publish(
            "System",
            f"Limit reached: the {label}. The run stops here and keeps its output so far.",
            "limit_reached",
            data={"cap": cap, "limit": limit},
        )
        raise Stopped(f"the {label} was reached")

    def _record(self, agent: Agent, text: str, usage: providers.Usage) -> None:
        self.tokens_in += usage.tokens_in
        self.tokens_out += usage.tokens_out
        self.cost_usd += usage.cost_usd or 0.0
        self._publish(
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
            self._warn(f"low:{provider}:{warning.split(':')[0]}", f"{provider} rate limit running low: {warning}")
        self._check_allowance(provider)

    def _check_allowance(self, provider: str) -> None:
        allowance = self.allowances.get(provider)
        if not allowance:
            return
        spent = store.spend_since(provider, month_start())
        line = f"{provider} has used ${spent:.2f} of its ${allowance:.2f} monthly allowance"
        if spent >= allowance:
            self._warn(f"allowance100:{provider}", f"{line}. New runs with it are blocked until next month.")
        elif spent >= 0.8 * allowance:
            self._warn(f"allowance80:{provider}", line)

    # ─── Pauses ──────────────────────────────────────────────

    def _replace_model(self, agent: Agent, error: providers.ProviderError) -> None:
        problem = error.problem
        assert problem is not None
        reason = f"{agent.name} can't continue on {agent.model}: {problem.message}."
        if self.fallback and self.fallback != agent.model and providers.is_local(self.fallback, self.endpoints):
            self._publish("System", f"{reason} Switching {agent.name} to {self.fallback}.", "warning")
            agent.model = self.fallback
            return
        choice = self._ask(
            f"{reason} Switch to another model and resume, or stop.",
            {"kind": "key_problem", "agent": agent.name, "model": agent.model, "problem": problem.kind},
            ["switch", "stop"],
        )
        if choice["action"] != "switch":
            raise Stopped("stopped at the paused decision")
        agent.model = choice["model"]
        self._publish("System", f"Resuming: {agent.name} now uses {agent.model}.", "system")

    def _ask(self, content: str, data: dict, options: list[str]) -> dict:
        """Pause until decide() answers (or the run is stopped)."""
        with self._lock:
            self._pending = {"options": options}
            while not self._decisions.empty():
                self._decisions.get_nowait()
        self.bus.set_task_status("paused")
        self._publish("System", content, "decision", data={**data, "options": options})
        try:
            while True:
                if self.cancel.is_set():
                    raise Stopped("stopped by the user")
                try:
                    choice = self._decisions.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.bus.set_task_status("running")
                return choice
        finally:
            with self._lock:
                self._pending = None

    # ─── Events ──────────────────────────────────────────────

    def _publish(self, agent_name: str, content: str, message_type: str, **fields) -> None:
        self.bus.publish(AgentMessage(agent_name=agent_name, content=content, message_type=message_type, **fields))

    def _warn(self, key: str, content: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self._publish("System", content, "warning")


# ─── The active run ──────────────────────────────────────────

_active: Run | None = None
_active_lock = threading.Lock()


def begin(project_id: str, run: Run) -> int | None:
    """Claim the bus for a run and create its run row. None if a task is already running."""
    if not run.bus.try_begin_task(run.prompt, project_id):
        return None
    try:
        crew_json = json.dumps([a.summary() for a in run.agents])
        run_id = store.create_run(project_id, run.prompt, run.mode, crew_json)
    except Exception:
        run.bus.set_task_status("error")
        raise
    run.bus.start_run(project_id, run_id)
    return run_id


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
    follow-ups as context. The question and answer are stored with the run."""
    agent = next(a for a in build_crew(settings) if a.name == agent_name)
    history = store.run_messages(run_row["id"])
    output = _transcript([(m["agent_name"], m["content"]) for m in history if m["message_type"] == "agent"])

    turns: list[dict] = []
    for m in history:
        if m["message_type"] not in ("question", "answer"):
            continue
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
    system = agent.prompt + "\n\n" + roles.PROTOCOL["follow_up"]

    parts: list[str] = []
    usage = None
    for item in providers.stream(
        agent.model,
        [{"role": "system", "content": system}, *turns],
        privacy=bool(settings["run"].get("privacy_mode")),
        max_tokens=agent.max_tokens,
        num_ctx=agent.num_ctx,
        endpoints=settings.get("endpoints"),
    ):
        if isinstance(item, providers.Usage):
            usage = item
        else:
            parts.append(item)
    reply = "".join(parts)
    tokens_in, tokens_out = (usage.tokens_in, usage.tokens_out) if usage else (0, 0)
    cost_usd = usage.cost_usd if usage else None

    project_id, run_id = run_row["project_id"], run_row["id"]
    store.save_message(project_id, run_id, {"agent_name": "You", "content": question, "message_type": "question"})
    store.save_message(
        project_id,
        run_id,
        {
            "agent_name": agent.name,
            "content": reply,
            "message_type": "answer",
            "model": agent.model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
        },
    )
    return {"agent": agent.name, "reply": reply, "model": agent.model, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost_usd}
