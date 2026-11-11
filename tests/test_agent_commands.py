import pytest
from typer.testing import CliRunner

from juli import cli, config, engine, providers, roles, store, workspace
from juli.bus import MessageBus

from .conftest import FakeProc, docker_up
from .test_engine import (
    APPROVED,
    Models,
    make_run,
    make_settings,
    of_type,
    run_in_thread,
    wait_for,
)

SANDBOX = {"enabled": True, "image": "python:3.12-slim", "timeout": 30}
CODE = "```python path=app.py\nprint(1)\n```\n```bash run\npytest -q\n```"
FIX = "```python path=app.py\nprint(2)\n```"


@pytest.fixture
def models(monkeypatch):
    fake = Models({"ollama:review": APPROVED, "ollama:code": CODE})
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
    return store.create_project("P")["id"]


def start(bus, project, mode="code", sandbox=None, **kwargs):
    settings = make_settings()
    if sandbox:
        settings["sandbox"] = sandbox
    run = make_run(bus, mode, settings, **kwargs)
    engine.begin(project, run)
    return run


def docker_runs(procs):
    return [a for a in procs.argvs() if a[:2] == ["docker", "run"]]


# ─── Files ───────────────────────────────────────────────────


def test_coder_files_land_in_the_workspace(models, bus, project):
    models.replies["ollama:code"] = "```python path=app.py\nprint(1)\n```\n```python path=../evil.py\nx\n```"
    models.replies["ollama:plan"] = "```python path=plan.py\nnot written\n```"  # planners don't write files
    run = start(bus, project)
    assert run.execute().status == "complete"

    base = workspace.root(project)
    assert (base / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    assert not (base / "plan.py").exists() and not (base.parent / "evil.py").exists()
    (files,) = of_type(bus, "files")
    assert files.agent_name == "Coder" and files.data == {"paths": ["app.py"]}
    assert any("Skipped '../evil.py' from Coder: '..' isn't allowed" in m.content for m in of_type(bus, "warning"))
    assert [f["path"] for f in store.run_files(run.run_id)] == ["app.py"]


def test_runs_without_a_workspace_skip_files_and_commands(models, bus, procs):
    assert make_run(bus, "code").execute().status == "complete"
    assert of_type(bus, "files") == [] and procs.calls == []


# ─── Approval ────────────────────────────────────────────────


def test_commands_ask_first_when_the_sandbox_is_off(models, bus, project, procs, monkeypatch):
    monkeypatch.setenv("JULI_TOKEN", "t")
    procs.handler = lambda argv: (b"1 passed\n", 0)
    run = start(bus, project)
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))

    (decision,) = of_type(bus, "decision")
    assert decision.data == {
        "kind": "command_approval",
        "agent": "Coder",
        "command": "pytest -q",
        "sandbox": False,
        "reason": "the Docker sandbox is off",
        "options": ["approve", "deny"],
    }
    assert decision.content.endswith("\n\npytest -q") and "outside any sandbox" in decision.content
    assert procs.calls == []  # nothing ran before the answer
    assert engine.decide("approve") is None
    thread.join(5)

    assert results[0].status == "complete"
    argv, kwargs = procs.calls[0]
    assert argv in ("pytest -q", ["/bin/sh", "-c", "pytest -q"])
    assert "JULI_TOKEN" not in kwargs["env"]
    (result,) = of_type(bus, "command")
    assert result.content == "$ pytest -q\nPassed\n\n1 passed" and result.data["status"] == "passed"
    # The output streamed live, but only the result stays in the history.
    assert [m.content for m in of_type(bus, "command_output")] == ["1 passed\n"]
    assert {m.message_type for m in bus.history} >= {"command", "command_start"}
    assert "command_output" not in {m.message_type for m in bus.history}


def test_a_denied_command_never_runs(models, bus, project, procs):
    procs.handler = lambda argv: (b"", 0)
    run = start(bus, project)
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    assert engine.decide("deny") is None
    thread.join(5)
    assert results[0].status == "complete" and procs.calls == []
    assert of_type(bus, "command")[0].content.startswith("$ pytest -q\nDenied")
    assert models.refs.count("ollama:code") == 1  # a denial isn't a failure to fix


def test_stop_at_a_command_approval(models, bus, project):
    run = start(bus, project)
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    engine.stop()
    thread.join(5)
    assert results[0].status == "stopped"


# ─── The sandbox ─────────────────────────────────────────────


def test_an_allowlisted_command_runs_on_its_own_in_the_sandbox(models, bus, project, procs):
    procs.handler = docker_up()
    run = start(bus, project, sandbox=SANDBOX)
    assert run.execute().status == "complete"
    assert of_type(bus, "decision") == []
    (argv,) = docker_runs(procs)
    assert argv[argv.index("--network") + 1] == "none" and argv[-3:] == ["python:3.12-slim", "pytest", "-q"]
    assert of_type(bus, "command_start")[0].data == {"command": "pytest -q", "sandbox": True}


def test_shell_metacharacters_ask_even_in_the_sandbox(models, bus, project, procs):
    models.replies["ollama:code"] = "```bash run\npytest -q; echo done\n```"
    procs.handler = docker_up()
    run = start(bus, project, sandbox=SANDBOX)
    thread, _ = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    data = of_type(bus, "decision")[0].data
    assert (data["sandbox"], data["reason"]) == (True, "it has shell metacharacters")
    engine.decide("approve")
    thread.join(5)
    assert docker_runs(procs)[0][-3:] == ["sh", "-c", "pytest -q; echo done"]


def test_sandbox_on_but_docker_missing_warns_and_asks(models, bus, project):
    run = start(bus, project, sandbox=SANDBOX)
    thread, _ = run_in_thread(run)
    wait_for(lambda: of_type(bus, "decision"))
    assert "Docker isn't installed" in of_type(bus, "decision")[0].data["reason"]
    assert any("Agent commands will ask first" in m.content for m in of_type(bus, "warning"))
    engine.decide("deny")
    thread.join(5)


# ─── Failures ────────────────────────────────────────────────


def test_a_failed_command_gets_one_fix_pass(models, bus, project, procs):
    codes = iter([(b"1 failed\n", 1), (b"1 passed\n", 0)])
    procs.handler = docker_up(lambda argv: next(codes))
    models.replies["ollama:code"] = [CODE, FIX]
    run = start(bus, project, sandbox=SANDBOX)
    assert run.execute().status == "complete"

    assert models.refs == ["ollama:plan", "ollama:code", "ollama:code", "ollama:review"]
    fix_call = models.calls[2]
    assert roles.PROTOCOL["fix"] in fix_call[1][0]["content"]
    brief = fix_call[1][1]["content"]
    assert "## Failed commands" in brief and "$ pytest -q\nFailed (exit code 1)\n\n1 failed" in brief
    assert len(docker_runs(procs)) == 2  # the failed command ran once more
    assert (workspace.root(project) / "app.py").read_text(encoding="utf-8") == "print(2)\n"
    assert [m.data["activity"] for m in of_type(bus, "turn_start") if m.agent_name == "Coder"] == ["coding", "fixing a failed command"]
    assert "print(2)" in models.calls[3][1][1]["content"]  # the reviewer sees the fix


def test_tester_failures_go_back_to_the_coder(models, bus, project, procs):
    codes = iter([(b"E assert\n", 1), (b"ok\n", 0)])
    procs.handler = docker_up(lambda argv: next(codes))
    models.replies["ollama:code"] = ["```python path=app.py\nprint(1)\n```", FIX]
    models.replies["ollama:test"] = "```python path=tests/test_app.py\ndef test(): pass\n```\n```bash run\npytest\n```"
    run = start(bus, project, mode="full", sandbox=SANDBOX)
    assert run.execute().status == "complete"
    assert models.refs[-4:] == ["ollama:devops", "ollama:test", "ollama:code", "ollama:docs"]
    assert (workspace.root(project) / "tests" / "test_app.py").exists()


def test_a_tool_missing_from_the_image_warns_without_a_fix_pass(models, bus, project, procs):
    procs.handler = docker_up(lambda argv: (b"exec: pytest: not found\n", 127))
    run = start(bus, project, sandbox=SANDBOX)
    assert run.execute().status == "complete"
    assert models.refs.count("ollama:code") == 1
    assert any("'pytest' isn't in the sandbox image python:3.12-slim" in m.content for m in of_type(bus, "warning"))


def test_a_sandbox_image_that_is_not_here_says_how_to_get_it(models, bus, project, procs):
    procs.handler = docker_up(lambda argv: (b"docker: Error response from daemon: No such image: python:3.12-slim\n", 125))
    run = start(bus, project, sandbox=SANDBOX)
    assert run.execute().status == "complete"
    assert models.refs.count("ollama:code") == 1  # no fix pass for a missing image
    warnings = [m.content for m in of_type(bus, "warning")]
    assert any("isn't on this machine" in w and "docker pull python:3.12-slim" in w for w in warnings)
    assert any(a[:2] == ["docker", "run"] and a[a.index("--pull") + 1] == "never" for a in procs.argvs())


def test_stop_while_a_command_runs(models, bus, project, procs):
    def handler(argv):
        return FakeProc(argv, b"collecting\n", block=True) if argv[:2] == ["docker", "run"] else (b"", 0)

    procs.handler = docker_up(handler)
    run = start(bus, project, sandbox=SANDBOX)
    thread, results = run_in_thread(run)
    wait_for(lambda: of_type(bus, "command_output"))
    engine.stop()
    thread.join(5)
    assert results[0].status == "stopped"
    assert any(a[:2] == ["docker", "kill"] for a in procs.argvs())


def test_cli_asks_before_running_a_command(models, procs):
    config.save_settings(make_settings())
    procs.handler = lambda argv: (b"1 passed\n", 0)
    result = CliRunner().invoke(cli.app, ["run", "Build it", "--code", "-o", str(config.data_dir() / "out")], input="y\n")
    text = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "Run this command?" in text and "$ pytest -q" in text and "Passed" in text
    assert procs.calls
