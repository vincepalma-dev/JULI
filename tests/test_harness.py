import json
import sys
import threading
import time
from pathlib import Path

import pytest

from juli import config, engine, harness, keystore, mcp, providers, store, tools, workspace
from juli.bus import MessageBus
from juli.providers import ToolCall, Usage

from .conftest import AUTH, FIXTURES, docker_up
from .test_engine import APPROVED, make_run, make_settings, of_type, run_in_thread, wait_for

MCP_SERVER = [sys.executable, str(FIXTURES / "mcp_server.py")]


def call(name, call_id=None, **args):
    return ToolCall(call_id or f"c-{name}-{len(json.dumps(args))}", name, json.dumps(args))


class ToolModels:
    """Fake providers.stream with tool calls. Each ref has a list of replies,
    used in turn (the last one repeats); a reply is text or a list of text
    and ToolCall items."""

    def __init__(self, script=None):
        self.script = {ref: list(replies) for ref, replies in (script or {}).items()}
        self.calls: list[tuple[str, list, dict]] = []

    def __call__(self, ref, messages, **kwargs):
        self.calls.append((ref, [dict(m) for m in messages], kwargs))
        replies = self.script.get(ref) or [APPROVED if ref == "ollama:review" else f"output of {ref}"]
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        yield from [reply] if isinstance(reply, str) else reply
        yield Usage(10, 5, 0.0)

    def of(self, ref):
        return [(messages, kwargs) for r, messages, kwargs in self.calls if r == ref]


@pytest.fixture
def models(monkeypatch):
    fake = ToolModels()
    monkeypatch.setattr(providers, "stream", fake)
    return fake


@pytest.fixture
def bus():
    bus = MessageBus()
    bus.events = []
    bus.subscribe_sync(bus.events.append)
    return bus


@pytest.fixture
def project():
    store.init_db()
    pid = store.create_project("P")["id"]
    base = workspace.ensure(pid)
    (base / "app.py").write_bytes(b"def add(a, b):\n    return a - b\n")  # bytes: the same size on every OS
    return pid


def start(bus, project, mode="code", settings=None, **kwargs):
    run = make_run(bus, mode, settings or make_settings(), **kwargs)
    engine.begin(project, run)
    return run


def tool_results(messages):
    return [m["content"] for m in messages if m["role"] == "tool"]


# ─── Middleware ──────────────────────────────────────────────


def test_chain_runs_layers_outermost_first():
    seen = []

    def layer(name):
        def middleware(call, call_next):
            seen.append(f"{name} in")
            result = call_next(call)
            seen.append(f"{name} out")
            return result

        return middleware

    handler = harness.chain([layer("a"), layer("b")], lambda call: seen.append(f"handler {call}") or "done")
    assert handler(1) == "done"
    assert seen == ["a in", "b in", "handler 1", "b out", "a out"]


def test_a_run_can_add_its_own_model_middleware(models, bus, project):
    logged = []
    run = start(bus, project)
    run.model_middleware.append(lambda call, call_next: logged.append(call.agent.name) or call_next(call))
    assert run.execute().status == "complete"
    assert logged == ["Planner", "Coder", "Reviewer"]


def test_every_tool_round_counts_against_the_token_cap(models, bus, project):
    models.script["ollama:code"] = [[call("list_files")], [call("read_file", path="app.py")], "done"]
    run = start(bus, project, settings=make_settings(token_cap=40))
    result = run.execute()
    assert result.status == "stopped"
    assert of_type(bus, "limit_reached")
    assert len(models.of("ollama:code")) < 3


def test_privacy_mode_is_checked_on_every_call(models, bus, project):
    settings = make_settings(privacy_mode=True)
    settings["agents"]["Coder"]["model"] = "openai:gpt-6.1-sol"
    run = start(bus, project, settings=settings)
    run.steps["coder"][0].model = "openai:gpt-6.1-sol"
    run.model_problem = lambda ref: None  # get past the preflight: the middleware still refuses
    assert run.execute().status == "error"
    assert "Privacy Mode is on" in of_type(bus, "error")[0].content
    assert "openai:gpt-6.1-sol" not in [r for r, _, _ in models.calls]


# ─── The tool loop ───────────────────────────────────────────


def test_an_agent_reads_a_file_then_answers(models, bus, project):
    models.script["ollama:code"] = [["Let me look. ", call("read_file", path="app.py")], "It subtracts; fixed."]
    assert start(bus, project).execute().status == "complete"

    first, second = models.of("ollama:code")
    names = [t["name"] for t in first[1]["tools"]]
    assert names == ["list_files", "read_file", "search_files", "write_file", "run_command", "handoff"]
    assert "You have tools" in first[0][0]["content"]
    assert tool_results(second[0]) == ["app.py, lines 1-2 of 2:\ndef add(a, b):\n    return a - b"]
    assistant = next(m for m in second[0] if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["name"] == "read_file"

    (tool,) = of_type(bus, "tool")
    assert tool.content == "read_file app.py" and tool.data["status"] == "ok"
    assert tool.data["args"] == {"path": "app.py"} and "return a - b" in tool.data["output"]
    assert [m.content for m in of_type(bus, "tool_start")] == ["read_file app.py"]
    coder_msgs = [m.content.strip() for m in of_type(bus, "agent") if m.agent_name == "Coder"]
    assert coder_msgs == ["Let me look.", "It subtracts; fixed."]


def test_write_file_writes_through_the_path_guard(models, bus, project):
    models.script["ollama:code"] = [
        [call("write_file", path="app.py", content="def add(a, b):\n    return a + b\n"), call("write_file", path="../x.py", content="x")],
        "Done.",
    ]
    run = start(bus, project)
    assert run.execute().status == "complete"
    base = workspace.root(project)
    assert "a + b" in (base / "app.py").read_text(encoding="utf-8")
    assert not (base.parent / "x.py").exists()
    results = tool_results(models.of("ollama:code")[1][0])
    assert results[0].startswith("Wrote app.py") and results[1] == "[error] ../x.py wasn't written: '..' isn't allowed."
    assert of_type(bus, "files")[0].data == {"paths": ["app.py"]}
    assert [f["path"] for f in store.run_files(run.run_id)] == ["app.py"]


def test_search_and_list(models, bus, project):
    models.script["ollama:plan"] = [[call("search_files", text="RETURN"), call("list_files", directory="nope")], "Plan."]
    assert start(bus, project).execute().status == "complete"
    found, listed = tool_results(models.of("ollama:plan")[1][0])
    assert found == "app.py:2: return a - b" and listed == "No files under nope."


def test_roles_only_get_their_own_tools(models, bus, project):
    models.script["ollama:plan"] = [[call("write_file", path="a.py", content="x")], "Plan."]
    assert start(bus, project).execute().status == "complete"
    offered = [t["name"] for t in models.of("ollama:plan")[0][1]["tools"]]
    assert offered == ["list_files", "read_file", "search_files"]
    reviewer = [t["name"] for t in models.of("ollama:review")[0][1]["tools"]]
    assert reviewer == ["list_files", "read_file", "search_files", "run_command", "handoff"]
    # A tool the role doesn't have isn't run, whatever the model asks for.
    assert tool_results(models.of("ollama:plan")[1][0]) == ["[error] Planner can't use 'write_file' in this step."]
    assert not (workspace.root(project) / "a.py").exists()


def test_bad_arguments_go_back_to_the_model(models, bus, project):
    models.script["ollama:code"] = [[ToolCall("1", "read_file", "{not json"), call("read_file"), call("read_file", path=3)], "ok"]
    assert start(bus, project).execute().status == "complete"
    assert tool_results(models.of("ollama:code")[1][0]) == [
        "[error] The arguments weren't a JSON object.",
        "[error] Wrong arguments for read_file: 'path' is required.",
        "[error] Wrong arguments for read_file: 'path' must be a string.",
    ]


def test_the_tool_round_limit_asks_for_a_final_answer(models, bus, project):
    settings = make_settings(max_tool_rounds=2)
    models.script["ollama:code"] = [[call("list_files", directory="a")], [call("list_files", directory="b")], [call("list_files")]]
    assert start(bus, project, settings=settings).execute().status == "complete"
    calls = models.of("ollama:code")
    assert len(calls) == 3
    assert calls[2][0][-1] == {"role": "user", "content": "You've used all 2 tool rounds for this turn. Give your final answer now."}
    assert len(of_type(bus, "tool")) == 2  # the last reply's tool call isn't run
    assert any("used all 2 tool rounds" in m.content for m in of_type(bus, "warning"))


def test_an_agent_can_have_its_own_round_limit(models, bus, project):
    settings = make_settings(max_tool_rounds=50)
    settings["agents"]["Coder"]["max_tool_rounds"] = 1
    models.script["ollama:code"] = [[call("list_files")], [call("list_files", directory="x")]]
    assert start(bus, project, settings=settings).execute().status == "complete"
    assert len(models.of("ollama:code")) == 2


def test_at_most_eight_tool_calls_per_reply(models, bus, project):
    models.script["ollama:code"] = [[call("read_file", path=f"f{i}.py") for i in range(10)], "ok"]
    assert start(bus, project).execute().status == "complete"
    results = tool_results(models.of("ollama:code")[1][0])
    assert len(results) == 10 and results[8:] == ["[error] Not run: at most 8 tool calls per reply."] * 2
    assert len(of_type(bus, "tool")) == 8


def test_the_repeat_guard_stops_identical_calls_until_something_changes(models, bus, project):
    read = call("read_file", path="app.py")
    write = call("write_file", path="app.py", content="x = 1\n")
    models.script["ollama:code"] = [[read, read, read, write, read], "ok"]
    assert start(bus, project).execute().status == "complete"
    results = tool_results(models.of("ollama:code")[1][0])
    assert results[2].startswith("[error] You already made this exact call 2 times")
    assert results[4].startswith("app.py, lines 1-1 of 1")  # the write changed things


def test_run_command_uses_the_command_policy(models, bus, project, procs):
    procs.handler = lambda argv: (b"1 failed\n", 1)
    models.script["ollama:code"] = [[call("run_command", command="pytest -q")], "I'll fix it."]
    run = start(bus, project)
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    assert of_type(bus, "decision")[0].data["kind"] == "command_approval"
    engine.decide("approve")
    thread.join(5)
    assert results[0].status == "complete"
    assert tool_results(models.of("ollama:code")[1][0]) == ["$ pytest -q\nFailed (exit code 1)\n\n1 failed"]
    assert of_type(bus, "command")[0].data["status"] == "failed"
    assert of_type(bus, "tool") == []  # the command events show it


def test_run_command_in_the_sandbox_runs_on_its_own(models, bus, project, procs):
    procs.handler = docker_up(lambda argv: (b"Error response from daemon: No such image: python:3.12-slim\n", 125))
    settings = make_settings()
    settings["sandbox"] = {"enabled": True, "image": "python:3.12-slim", "timeout": 30}
    models.script["ollama:code"] = [[call("run_command", command="pytest -q")], "ok"]
    assert start(bus, project, settings=settings).execute().status == "complete"
    assert of_type(bus, "decision") == []
    assert tool_results(models.of("ollama:code")[1][0])[0].startswith("[error] $ pytest -q\nDidn't run")
    assert any("isn't on this machine, and JULI doesn't download images" in m.content for m in of_type(bus, "warning"))


def test_models_without_tools_get_none_offered(models, bus, project, monkeypatch):
    monkeypatch.setattr(providers, "_NO_TOOLS", {"ollama:code"})
    assert start(bus, project).execute().status == "complete"
    _, kwargs = models.of("ollama:code")[0]
    assert kwargs["tools"] is None
    assert "You have tools" not in models.of("ollama:code")[0][0][0]["content"]


def test_no_tools_without_a_workspace(models, bus):
    assert make_run(bus, "code").execute().status == "complete"
    assert all(kwargs["tools"] is None for _, _, kwargs in models.calls)


def test_stop_between_tool_calls(models, bus, project):
    run = start(bus, project)
    original = tools.run_read

    def read_then_stop(*args):
        run.stop()
        return original(*args)

    tools.run_read = read_then_stop
    try:
        models.script["ollama:code"] = [[call("list_files"), call("read_file", path="app.py")], "ok"]
        assert run.execute().status == "stopped"
    finally:
        tools.run_read = original
    assert len(of_type(bus, "tool")) == 1


# ─── Handoffs ────────────────────────────────────────────────


def test_tester_hands_a_failure_to_the_coder_and_carries_on(models, bus, project):
    models.script["ollama:test"] = [[call("handoff", to="coder", reason="test_add fails: add() subtracts")], "Tests pass now."]
    models.script["ollama:code"] = ["code v1", "Fixed add()."]
    run = start(bus, project, mode="full")
    assert run.execute().status == "complete"

    handoff_brief = models.of("ollama:code")[1][0][1]["content"]
    assert "## Handoff from Tester\n\ntest_add fails: add() subtracts" in handoff_brief
    assert tool_results(models.of("ollama:test")[1][0]) == ["Fixed add()."]
    assert any(m.content == "Tester hands off to Coder: test_add fails: add() subtracts" for m in of_type(bus, "system"))
    assert of_type(bus, "tool")[0].content == "handoff coder"
    assert run.handoffs == 1


def test_handoff_guards(models, bus, project):
    settings = make_settings(max_handoffs=1)
    models.script["ollama:test"] = [
        [call("handoff", to="Nobody", reason="x"), call("handoff", to="tester", reason="x"), call("handoff", to="Coder", reason="fix")],
        [call("handoff", to="Coder", reason="again")],
        "done",
    ]
    # While Tester waits on its handoff, Coder can't hand back to it.
    models.script["ollama:code"] = ["code v1", [call("handoff", to="Tester", reason="back")], "fixed"]
    assert start(bus, project, mode="full", settings=settings).execute().status == "complete"

    first = tool_results(models.of("ollama:test")[1][0])
    assert first[0].startswith("[error] No one called 'Nobody' is in this crew. Colleagues: Planner (planner), Coder (coder)")
    assert first[1] == "[error] You can't hand off to yourself."
    assert first[2] == "fixed"
    coder_results = tool_results(models.of("ollama:code")[2][0])
    assert coder_results == ["[error] Tester is waiting for your reply to their handoff. Finish your part and reply instead."]
    second = tool_results(models.of("ollama:test")[2][0])
    assert second[-1] == "[error] The handoff limit for this run (1) is reached. Complete your step yourself."


def test_handoffs_between_two_agents_stop_at_max_cycles(models, bus, project):
    models.script["ollama:test"] = [[call("handoff", to="Coder", reason=f"fix {i}") for i in range(3)], "done"]
    assert start(bus, project, mode="full", max_cycles=2).execute().status == "complete"
    results = tool_results(models.of("ollama:test")[1][0])
    assert results[2] == "[error] You and Coder have handed work to each other 2 times already. Complete your step yourself."


def test_no_handoff_tool_when_handoffs_are_off_or_alone(models, bus, project):
    assert start(bus, project, settings=make_settings(max_handoffs=0)).execute().status == "complete"
    assert "handoff" not in [t["name"] for t in models.of("ollama:code")[0][1]["tools"]]


# ─── Checkpoints ─────────────────────────────────────────────


def test_a_resumed_run_replays_tool_steps_without_running_them(models, bus, project, monkeypatch):
    models.script["ollama:code"] = [
        [call("write_file", path="new.py", content="v1\n"), call("read_file", path="app.py")],
        [call("handoff", to="Reviewer", reason="look")],
        "final",
    ]
    run = start(bus, project)
    assert run.execute().status == "complete"
    state = run.checkpoint()
    kinds = [s["kind"] for s in state["steps"]]
    assert kinds == ["turn", "reply", "tool", "tool", "reply", "turn", "turn", "turn"]

    # Cut the checkpoint inside the coder's turn, after its handoff came back.
    state["steps"] = state["steps"][:6]
    (workspace.root(project) / "new.py").write_text("changed since\n", encoding="utf-8")
    fresh = ToolModels({"ollama:code": ["final after resume"]})
    monkeypatch.setattr(providers, "stream", fresh)
    bus2 = MessageBus()
    bus2.events = []
    bus2.subscribe_sync(bus2.events.append)
    resumed = engine.Run.from_checkpoint(state, settings=make_settings(), bus=bus2)
    engine.begin(project, resumed, run_id=run.run_id)
    assert resumed.execute().status == "complete"

    assert (workspace.root(project) / "new.py").read_text(encoding="utf-8") == "changed since\n"  # not written again
    refs = [r for r, _, _ in fresh.calls]
    assert refs == ["ollama:code", "ollama:review"]  # only the coder's last call and the review run live
    replayed_history = fresh.of("ollama:code")[0][0]
    assert tool_results(replayed_history)[0].startswith("Wrote new.py")
    assert resumed.handoffs == 1
    assert of_type(bus2, "tool") == [] and of_type(bus2, "files") == []


# ─── Follow-up ───────────────────────────────────────────────


def test_follow_up_answers_can_read_the_workspace(models, project):
    run_id = store.create_run(project, "Build", "code")
    store.finish_run(run_id, "complete")
    models.script["ollama:code"] = [[call("read_file", path="app.py"), call("write_file", path="x", content="y")], "It subtracts."]
    reply = engine.follow_up(store.get_run(run_id), "Coder", "What does add do?", make_settings())
    assert reply["reply"] == "It subtracts."
    assert reply["tokens_in"] == 20 and reply["cost_usd"] == 0.0
    results = tool_results(models.of("ollama:code")[1][0])
    assert results[0].startswith("app.py, lines 1-2") and results[1] == "[error] 'write_file' can't be used in a follow-up."
    assert [t["name"] for t in models.of("ollama:code")[0][1]["tools"]] == list(tools.READ)


def test_follow_up_answers_every_call_and_asks_to_finish_at_the_limit(models, project):
    run_id = store.create_run(project, "Build", "code")
    store.finish_run(run_id, "complete")
    settings = make_settings(max_tool_rounds=1)
    models.script["ollama:code"] = [[call("list_files", directory=f"d{i}") for i in range(10)], "Done."]
    assert engine.follow_up(store.get_run(run_id), "Coder", "Where is it?", settings)["reply"] == "Done."
    last = models.of("ollama:code")[1][0]
    results = tool_results(last)
    assert len(results) == 10 and results[8:] == ["[error] Not run: at most 8 tool calls per reply."] * 2
    assert last[-1] == {"role": "user", "content": "You've used all 1 tool rounds for this turn. Give your final answer now."}


# ─── Read-only tools ─────────────────────────────────────────


def test_read_file_ranges_and_refusals(project):
    base = workspace.root(project)
    (base / "long.txt").write_text("\n".join(f"line {i}" for i in range(1, 1001)), encoding="utf-8")
    (base / "bin.dat").write_bytes(b"\xff\xfe\x00")
    assert tools.read_file(project, "long.txt", 10, 12) == "long.txt, lines 10-12 of 1000:\nline 10\nline 11\nline 12"
    assert tools.read_file(project, "long.txt").startswith(f"long.txt, lines 1-{tools.MAX_READ_LINES} of 1000")
    for path, start, end, message in [
        ("nope.py", 1, None, "nope.py doesn't exist"),
        ("bin.dat", 1, None, "bin.dat is binary"),
        ("long.txt", 2000, None, "long.txt has only 1000 lines"),
        ("long.txt", 5, 2, "end_line is before start_line"),
    ]:
        with pytest.raises(tools.ToolError, match=message):
            tools.read_file(project, path, start, end)
    with pytest.raises(workspace.PathRefused):
        tools.read_file(project, ".git/config")


def test_search_skips_binary_and_dependency_folders(project):
    base = workspace.root(project)
    (base / "node_modules").mkdir()
    (base / "node_modules" / "lib.js").write_text("return a - b", encoding="utf-8")
    (base / "src").mkdir()
    (base / "src" / "b.py").write_text("x = 'return a - b'\n", encoding="utf-8")
    assert tools.search_files(project, "a - b") == "app.py:2: return a - b\nsrc/b.py:1: x = 'return a - b'"
    assert tools.search_files(project, "a - b", "src") == "src/b.py:1: x = 'return a - b'"
    assert tools.search_files(project, "zzz") == "No matches for 'zzz'."
    with pytest.raises(tools.ToolError):
        tools.search_files(project, "  ")


def test_list_files(project):
    assert tools.list_files(project) == "app.py  (32 bytes)"
    assert tools.list_files(project, "./") == "app.py  (32 bytes)"


def test_check_args():
    schema = tools.BUILTIN["read_file"].parameters
    assert tools.check_args(schema, {"path": "a", "start_line": 2}) is None
    assert tools.check_args(schema, {"path": "a", "start_line": True}) == "'start_line' must be a whole number"


# ─── Provider wire formats ───────────────────────────────────

SSE = {"content-type": "text/event-stream"}
MESSAGES = [
    {"role": "system", "content": "Be brief."},
    {"role": "user", "content": "Fix it"},
    {"role": "assistant", "content": "Reading.", "tool_calls": [{"id": "t1", "name": "read_file", "arguments": '{"path": "app.py"}'}]},
    {"role": "tool", "tool_call_id": "t1", "name": "read_file", "content": "def add(): ..."},
    {"role": "user", "content": "Finish now."},
]
TOOLS = [tools.BUILTIN["read_file"].schema()]


def sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def test_openai_tool_calls_stream_in_pieces(net):
    keystore.set_key("openai", "sk-test-aaaabbbb")
    base = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "m"}
    piece = lambda delta: {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
    body = sse(
        piece({"role": "assistant", "content": "Sure. "}),
        piece({"tool_calls": [{"index": 0, "id": "call_9", "type": "function", "function": {"name": "read_file", "arguments": ""}}]}),
        piece({"tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]}),
        piece({"tool_calls": [{"index": 0, "function": {"arguments": ' "app.py"}'}}]}),
        {**base, "choices": [], "usage": {"prompt_tokens": 30, "completion_tokens": 9, "total_tokens": 39}},
    )
    net.handler = lambda req: (200, body, SSE)
    items = list(providers.stream("openai:gpt-6.1-sol", MESSAGES, tools=TOOLS))
    assert items[0] == "Sure. "
    assert items[1] == ToolCall("call_9", "read_file", '{"path": "app.py"}')
    assert (items[2].tokens_in, items[2].tokens_out) == (30, 9)

    sent = json.loads(net.requests[0].content)
    assert sent["tools"] == [{"type": "function", "function": TOOLS[0]}]
    assert sent["messages"][2] == {
        "role": "assistant",
        "content": "Reading.",
        "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "app.py"}'}}],
    }
    assert sent["messages"][3] == {"role": "tool", "tool_call_id": "t1", "content": "def add(): ..."}


def test_anthropic_tool_use_blocks(net):
    keystore.set_key("anthropic", "sk-ant-test-ccccdddd")
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "m",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-5-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 50, "output_tokens": 1},
                },
            },
        ),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Reading."}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {}},
            },
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"path": "app.py"}'}},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        (
            "message_delta",
            {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 20}},
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
    net.handler = lambda req: (200, body, SSE)
    items = list(providers.stream("anthropic:claude-sonnet-5-5", MESSAGES, tools=TOOLS))
    assert items[0] == "Reading."
    assert items[1] == ToolCall("toolu_1", "read_file", '{"path": "app.py"}')

    sent = json.loads(net.requests[0].content)
    assert sent["tools"] == [{"name": "read_file", "description": TOOLS[0]["description"], "input_schema": TOOLS[0]["parameters"]}]
    assert sent["messages"][1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Reading."},
            {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "app.py"}},
        ],
    }
    # The tool result and the next user message share one user turn.
    assert sent["messages"][2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "def add(): ..."}, {"type": "text", "text": "Finish now."}],
    }


def test_ollama_tool_calls(net):
    lines = [
        {
            "model": "qwen3:8b",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "app.py"}}}],
            },
            "done": False,
        },
        {"model": "qwen3:8b", "message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 30, "eval_count": 9},
    ]
    net.handler = lambda req: (200, "\n".join(json.dumps(line) for line in lines), {"content-type": "application/x-ndjson"})
    items = list(providers.stream("ollama:qwen3:8b", MESSAGES, tools=TOOLS))
    assert (items[0].name, items[0].arguments) == ("read_file", '{"path": "app.py"}')
    # Ollama sends no ids: each call gets its own, so a nested call can't match its caller's.
    again = list(providers.stream("ollama:qwen3:8b", MESSAGES, tools=TOOLS))
    assert items[0].id.startswith("call_") and items[0].id != again[0].id
    sent = json.loads(net.requests[0].content)
    assert sent["tools"][0]["function"]["name"] == "read_file"
    assert sent["messages"][2]["tool_calls"] == [{"function": {"name": "read_file", "arguments": {"path": "app.py"}}}]
    assert sent["messages"][3] == {"role": "tool", "content": "def add(): ...", "tool_name": "read_file"}


def test_a_model_that_refuses_tools_falls_back_to_text(net, monkeypatch):
    monkeypatch.setattr(providers, "_NO_TOOLS", set())
    done = {"model": "tiny", "message": {"role": "assistant", "content": "plain"}, "done": True, "prompt_eval_count": 1, "eval_count": 1}

    def handler(req):
        if "tools" in json.loads(req.content):
            return 400, {"error": "registry.ollama.ai/library/tiny does not support tools"}, {}
        return 200, json.dumps(done), {}

    net.handler = handler
    assert next(iter(providers.stream("ollama:tiny", MESSAGES[:2], tools=TOOLS))) == "plain"
    assert len(net.requests) == 2 and not providers.supports_tools("ollama:tiny")
    list(providers.stream("ollama:tiny", MESSAGES[:2], tools=TOOLS))
    assert len(net.requests) == 3  # remembered: no second try with tools


@pytest.mark.parametrize(
    "status, error",
    [
        (404, "model 'nope' not found"),
        (400, "invalid tool_call_id: t9"),  # a bad tool request, not a model without tools
        (429, "too many requests: tools does not support tools"),
    ],
)
def test_other_errors_with_tools_are_not_a_fallback(net, monkeypatch, status, error):
    monkeypatch.setattr(providers, "_NO_TOOLS", set())
    net.handler = lambda req: (status, {"error": error}, {})
    with pytest.raises(providers.ProviderError):
        list(providers.stream("ollama:nope", MESSAGES[:2], tools=TOOLS))
    assert providers.supports_tools("ollama:nope")


@pytest.mark.parametrize(
    "error",
    [
        "tools param requires --jinja flag",
        '"auto" tool choice requires --enable-auto-tool-choice',
        "No endpoints found that support tool use",
    ],
)
def test_other_servers_wording_for_no_tools(error):
    assert providers._rejects_tools(400, {"error": {"message": error}})


def test_no_fallback_once_the_conversation_has_tool_calls(net, monkeypatch):
    monkeypatch.setattr(providers, "_NO_TOOLS", set())
    net.handler = lambda req: (400, {"error": "registry.ollama.ai/library/tiny does not support tools"}, {})
    with pytest.raises(providers.ToolsUnsupported):
        list(providers.stream("ollama:tiny", MESSAGES, tools=TOOLS))
    assert len(net.requests) == 1 and providers.supports_tools("ollama:tiny")


# ─── MCP ─────────────────────────────────────────────────────


def mcp_settings(**server):
    settings = make_settings()
    settings["mcp_servers"] = {"fake": {"transport": "stdio", "command": MCP_SERVER, "enabled": True, **server}}
    return settings


def test_mcp_tools_need_approval(models, bus, project):
    models.script["ollama:code"] = [[call("mcp__fake__echo", text="hi"), call("mcp__fake__fail")], "ok"]
    run = start(bus, project, settings=mcp_settings())
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    decision = of_type(bus, "decision")[0]
    assert decision.data == {
        "kind": "tool_approval",
        "agent": "Coder",
        "tool": "echo",
        "server": "fake",
        "args": {"text": "hi"},
        "sandbox": False,
        "reason": "its server runs on this machine, outside the sandbox",
        "options": ["approve", "deny"],
    }
    engine.decide("approve")
    wait_for(lambda: len(of_type(bus, "decision")) == 2)
    engine.decide("deny")
    thread.join(10)
    assert results[0].status == "complete"
    assert tool_results(models.of("ollama:code")[1][0]) == ["echo: hi", "[denied] The user denied this call."]
    offered = [t["name"] for t in models.of("ollama:code")[0][1]["tools"]]
    assert offered[-3:] == ["mcp__fake__echo", "mcp__fake__fail", "mcp__fake__env"]
    assert [m.data["server"] for m in of_type(bus, "tool")] == ["fake", "fake"]
    assert run._mcp is None  # closed when the run ended


def test_trusted_tools_still_ask_when_the_server_is_unsandboxed(models, bus, project):
    models.script["ollama:code"] = [[call("mcp__fake__echo", text="hi")], "ok"]
    run = start(bus, project, settings=mcp_settings(trusted_tools=["echo"]))
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    assert of_type(bus, "decision")[0].data["kind"] == "tool_approval"
    engine.decide("approve")
    thread.join(10)
    assert results[0].status == "complete"


def test_mcp_server_errors_and_roles(models, bus, project):
    models.script["ollama:code"] = [[call("mcp__fake__fail")], "ok"]
    run = start(bus, project, settings=mcp_settings(roles=["coder"]))
    thread, _ = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    engine.decide("approve")
    thread.join(10)
    assert tool_results(models.of("ollama:code")[1][0]) == ["[error] it broke"]
    assert not any(t["name"].startswith("mcp__") for t in models.of("ollama:review")[0][1]["tools"])


def test_mcp_token_goes_to_the_named_variable(project, memory_keyring):
    keystore.set_key(mcp.token_key("fake"), "t")
    server = mcp.Server("fake", {"transport": "stdio", "command": MCP_SERVER, "token_env": "FAKE_TOKEN"})
    server.start(workspace.root(project), {})
    try:
        assert server.call("env", {"name": "FAKE_TOKEN"}) == ("set", False)
        assert server.call("env", {"name": "JULI_DATA_DIR"}) == ("unset", False)  # safe_env strips JULI_*
    finally:
        server.close()


def test_a_server_that_wont_start_is_skipped_with_a_warning(models, bus, project):
    settings = mcp_settings(command=[sys.executable, "-c", "import sys; sys.stderr.write('boom\\n')"])
    assert start(bus, project, settings=settings).execute().status == "complete"
    assert any("The MCP server fake didn't start: the server exited: boom." == m.content for m in of_type(bus, "warning"))
    assert not any(t["name"].startswith("mcp__") for t in models.of("ollama:code")[0][1]["tools"])


@pytest.mark.parametrize(
    "cfg, privacy, off, problem",
    [
        ({"transport": "http", "url": "https://mcp.example.com/mcp"}, True, None, "Privacy Mode is on and its URL isn't"),
        ({"transport": "http", "url": "http://127.0.0.1:9000/mcp"}, True, None, None),
        ({"transport": "stdio", "command": ["x"]}, True, None, "Privacy Mode is on, and outside the sandbox"),
        ({"transport": "stdio", "command": ["x"]}, False, None, None),
        (
            {"transport": "stdio", "command": ["x"], "sandbox": True},
            True,
            "the Docker sandbox is off",
            "it runs in the sandbox, and the Docker",
        ),
        ({"transport": "stdio", "command": ["x"], "sandbox": True}, True, None, None),
    ],
)
def test_privacy_mode_and_the_sandbox_decide_which_servers_start(cfg, privacy, off, problem):
    found = mcp.start_problem(cfg, privacy=privacy, sandbox_off=off)
    assert found == problem if problem is None else found.startswith(problem)


def test_privacy_mode_keeps_a_cloud_mcp_server_out_of_the_run(models, bus, project, net):
    settings = make_settings(privacy_mode=True)
    settings["mcp_servers"] = {"cloud": {"transport": "http", "url": "https://mcp.example.com/mcp", "enabled": True}}
    assert start(bus, project, settings=settings).execute().status == "complete"
    assert net.requests == []
    assert any(m.content.startswith("The MCP server cloud isn't used in this run: Privacy Mode is on") for m in of_type(bus, "warning"))


def test_a_sandboxed_server_runs_in_docker_with_the_token_by_name(project, procs, monkeypatch):
    started = []

    class Started(Exception):
        pass

    def fake_popen(argv, **kwargs):
        started.append((argv, kwargs))
        raise Started

    monkeypatch.setattr(mcp, "POPEN", fake_popen)
    monkeypatch.setattr(mcp, "_Stdio", lambda argv, env, cwd, container: fake_popen(argv, env=env))
    keystore.set_key(mcp.token_key("gh"), "secret-token-value")
    server = mcp.Server("gh", {"transport": "stdio", "command": ["node", "server.js"], "sandbox": True, "token_env": "GH_TOKEN"})
    with pytest.raises(Started):
        server.start(workspace.root(project), {"image": "node:22-slim", "timeout": 30})
    argv, kwargs = started[0]
    assert argv[:4] == ["docker", "run", "--rm", "-i"]
    assert "--pull" in argv and "never" in argv and "none" in argv
    assert argv[-3:] == ["node:22-slim", "node", "server.js"]
    assert argv[argv.index("-e", argv.index("HOME=/tmp")) + 1] == "GH_TOKEN"
    assert "secret-token-value" not in " ".join(argv)
    assert kwargs["env"]["GH_TOKEN"] == "secret-token-value"


def test_mcp_over_http(net, project):
    seen = []

    def handler(req):
        body = json.loads(req.content) if req.content else {}
        seen.append((req.method, body.get("method"), dict(req.headers)))
        if req.method == "DELETE" or "id" not in body:
            return 202, "", {}
        if body["method"] == "initialize":
            return 200, {"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-06-18"}}, {"mcp-session-id": "s1"}
        if body["method"] == "tools/list":
            result = {"tools": [{"name": "lookup.v2", "description": "Look up", "inputSchema": {"type": "object"}}]}
            return 200, {"jsonrpc": "2.0", "id": body["id"], "result": result}, {}
        event = {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": "found"}, {"type": "image"}]}}
        return 200, f"event: message\ndata: {json.dumps(event)}\n\n", SSE

    net.handler = handler
    keystore.set_key(mcp.token_key("docs"), "tok")
    server = mcp.Server("docs", {"transport": "http", "url": "http://127.0.0.1:9000/mcp"})
    (tool,) = server.start(None, {})
    assert tool.full_name == "mcp__docs__lookup_v2" and tool.name == "lookup.v2"
    assert server.call("lookup.v2", {"q": "x"}) == ("found\n[image content]", False)
    server.close()

    assert seen[0][2]["authorization"] == "Bearer tok"
    assert seen[2][2]["mcp-session-id"] == "s1" and seen[2][2]["mcp-protocol-version"] == "2025-06-18"
    assert [s[1] for s in seen] == ["initialize", "notifications/initialized", "tools/list", "tools/call", None]


def test_mcp_http_errors(net):
    net.handler = lambda req: (500, "", {})
    with pytest.raises(mcp.McpError, match="HTTP 500"):
        mcp.Server("x", {"transport": "http", "url": "http://127.0.0.1:1/mcp"}).start(None, {})


def test_stop_ends_a_slow_http_mcp_call(net):
    release = threading.Event()

    def handler(req):
        body = json.loads(req.content) if req.content else {}
        if "id" not in body:
            return 202, "", {}  # a notification, or the closing DELETE
        if body["method"] == "tools/call":
            release.wait(10)  # a slow tool
        return 200, {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [], "content": []}}, {}

    net.handler = handler
    server = mcp.Server("slow", {"transport": "http", "url": "http://127.0.0.1:9000/mcp"})
    server.start(None, {})
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    try:
        with pytest.raises(mcp.McpError, match="stopped"):
            server.call("wait", {}, cancel)
        assert time.monotonic() - started < 3
    finally:
        release.set()
        server.close()


@pytest.mark.parametrize(
    "result, text",
    [
        ({"content": "plain text"}, "plain text"),
        ({"content": ["a string", {"type": "text", "text": "kept"}, 3]}, "kept"),
        ({"content": {"type": "text"}}, ""),
    ],
)
def test_a_malformed_mcp_result_is_read_as_far_as_it_can_be(result, text):
    assert mcp._text(result) == text


# ─── Settings ────────────────────────────────────────────────


def test_mcp_settings_keep_tokens_in_the_keychain(client, memory_keyring):
    servers = {
        "fake": {"transport": "stdio", "command": ["npx", "-y", "server"], "token_env": "API_TOKEN"},
        "docs": {"transport": "http", "url": "http://127.0.0.1:9000/mcp", "trusted_tools": ["lookup"]},
    }
    r = client.put("/api/settings/mcp", json=servers, headers=AUTH)
    assert r.status_code == 200, r.text
    assert client.put("/api/settings/mcp/fake/token", json={"token": "secret-value-1234"}, headers=AUTH).json()["token_hint"] == "••••1234"
    body = client.get("/api/settings", headers=AUTH).json()
    assert body["mcp_servers"]["fake"]["token_hint"] == "••••1234"
    assert body["mcp_servers"]["docs"]["trusted_tools"] == ["lookup"]
    assert "secret-value-1234" not in Path(config.settings_path()).read_text(encoding="utf-8")

    # Removing a server removes its token.
    assert client.put("/api/settings/mcp", json={"docs": servers["docs"]}, headers=AUTH).status_code == 200
    assert keystore.get_key(mcp.token_key("fake")) is None
    assert client.put("/api/settings/mcp/fake/token", json={"token": "x"}, headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "server",
    [
        {"transport": "stdio"},
        {"transport": "http", "url": "ftp://x"},
        {"transport": "http"},
        {"transport": "stdio", "command": ["x"], "roles": ["boss"]},
        {"transport": "stdio", "command": ["x"], "token_env": "BAD-NAME"},
        {"transport": "stdio", "command": ["x"], "api_key": "k"},
    ],
)
def test_mcp_settings_validation(client, server):
    assert client.put("/api/settings/mcp", json={"s": server}, headers=AUTH).status_code == 422


@pytest.mark.parametrize("name", ["Bad Name", "a__b", "a_", "_a", "x" * 25])
def test_mcp_server_names_are_checked(client, name):
    assert client.put("/api/settings/mcp", json={name: {"command": ["x"]}}, headers=AUTH).status_code == 422
    assert client.put("/api/settings/mcp", json={"my_server_2": {"command": ["x"]}}, headers=AUTH).status_code == 200


def test_agent_tool_rounds_can_be_set_and_cleared(client):
    assert client.put("/api/settings/agents", json={"Coder": {"max_tool_rounds": 5}}, headers=AUTH).status_code == 200
    assert client.get("/api/settings", headers=AUTH).json()["agents"]["Coder"]["max_tool_rounds"] == 5
    client.put("/api/settings/agents", json={"Coder": {"max_tool_rounds": None}}, headers=AUTH)
    assert client.get("/api/settings", headers=AUTH).json()["agents"]["Coder"]["max_tool_rounds"] is None
    assert client.put("/api/settings/agents", json={"Coder": {"max_tool_rounds": 500}}, headers=AUTH).status_code == 422


def test_cli_shows_tools_and_asks_before_an_mcp_call(models):
    from typer.testing import CliRunner

    from juli import cli

    config.save_settings(mcp_settings())
    models.script["ollama:code"] = [[call("list_files", directory="nope"), call("mcp__fake__echo", text="hi")], "ok"]
    result = CliRunner().invoke(cli.app, ["run", "Build it", "--code", "-o", str(config.data_dir() / "out")], input="y\n")
    text = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "→ list_files nope" in text and "Allow this tool call?" in text and "echo: hi" not in text
    assert tool_results(models.of("ollama:code")[1][0])[1] == "echo: hi"
