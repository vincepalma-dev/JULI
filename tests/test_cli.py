"""The CLI's run loop (answering pauses), follow-up questions, workspace
commands and the dashboard build, end to end through Typer."""

import subprocess

import pytest
from typer.testing import CliRunner

from juli import cli, config, engine, store, workspace
from juli.providers import KeyProblem, ProviderError

from .conftest import serve
from .test_catalogue import LLAMA_REPO, hf_routes
from .test_engine import APPROVED, Models, make_settings
from .test_workspace import git, needs_git, new_run


@pytest.fixture
def models(monkeypatch):
    fake = Models({"ollama:review": APPROVED})
    monkeypatch.setattr(cli.engine.providers, "stream", fake)
    config.save_settings(make_settings())
    return fake


def invoke(*args, **kwargs):
    result = CliRunner().invoke(cli.app, list(args), **kwargs)
    result.text = " ".join(result.output.split())  # rich wraps long lines
    return result


def run(*args, **kwargs):
    return invoke("run", "Build it", *args, "-o", str(config.data_dir() / "out"), **kwargs)


# ─── Answering pauses ────────────────────────────────────────


def test_plan_approval_approve(models):
    result = run("--code", "--approve-plan", input="y\n")
    assert result.exit_code == 0, result.output
    assert "Approve the plan?" in result.text and "Run complete" in result.text
    assert models.refs.count("ollama:plan") == 1 and "ollama:code" in models.refs


def test_plan_approval_revise_then_approve(models):
    models.replies["ollama:plan"] = ["First plan", "Plan with SQLite"]
    result = run("--code", "--approve-plan", input="Use SQLite\ny\n")
    assert result.exit_code == 0, result.output
    assert models.refs.count("ollama:plan") == 2
    revise = models.calls[models.refs.index("ollama:plan", 1)][1]
    assert any("Use SQLite" in m["content"] for m in revise)  # the user's idea reaches the planner


def test_plan_approval_stop(models):
    result = run("--code", "--approve-plan", input="n\n")
    assert "ollama:code" not in models.refs
    assert "stopped" in result.text.lower()


def test_key_problem_asks_for_a_model_and_retries_a_refused_one(models):
    models.replies["ollama:code"] = [ProviderError("openai", "bad key", KeyProblem("invalid", "the API key was rejected")), "fixed"]
    config.save_settings(make_settings(privacy_mode=True))
    # A cloud model is refused in Privacy Mode, so the prompt comes back; then a local one resumes.
    result = run("--code", input="openai:gpt-6.1-sol\nollama:spare\n")
    assert result.exit_code == 0, result.output
    assert result.text.count("Switch to which model") == 2 and "Privacy Mode" in result.text
    assert "ollama:spare" in models.refs and "Run complete" in result.text


def test_key_problem_with_no_model_stops(models):
    models.replies["ollama:code"] = ProviderError("openai", "bad key", KeyProblem("invalid", "the API key was rejected"))
    result = run("--code", input="\n")
    assert "ollama:review" not in models.refs
    assert "stopped" in result.text.lower()


def test_a_used_up_allowance_blocks_unless_ignored(models, monkeypatch):
    monkeypatch.setattr(engine, "allowance_report", lambda agents, settings: ([], ["openai: $10.00 of $10.00"]))
    blocked = run("--plan")
    assert blocked.exit_code == 1 and "Monthly allowance reached: openai: $10.00 of $10.00." in blocked.text
    assert models.calls == []
    assert run("--plan", "--ignore-allowance").exit_code == 0


# ─── Follow-up questions ─────────────────────────────────────


def test_ask_about_the_latest_run(models):
    assert run("--plan").exit_code == 0
    models.replies["ollama:code"] = "Because it is simpler."
    result = invoke("ask", "Why this design?", "--agent", "Coder")
    assert result.exit_code == 0, result.output
    assert "Because it is simpler." in result.text and "100 tokens in · 50 out" in result.text
    question = models.calls[-1][1][-1]["content"]
    assert "Why this design?" in question


def test_ask_errors(models):
    assert "No finished run to ask about" in invoke("ask", "Why?", "--agent", "Planner").text
    assert run("--plan").exit_code == 0
    assert "No agent named Nobody" in invoke("ask", "Why?", "--agent", "Nobody").text
    models.replies["ollama:plan"] = ProviderError("ollama", "can't reach Ollama at http://127.0.0.1:11434")
    failed = invoke("ask", "Why?", "--agent", "Planner")
    assert failed.exit_code == 1 and "can't reach Ollama" in failed.text


# ─── Workspace ───────────────────────────────────────────────


def test_workspace_commands_without_runs_or_files():
    store.init_db()
    assert "The workspace is empty." in invoke("workspace", "tree").text
    assert "This project has no runs yet." in invoke("workspace", "diff").text
    pid = store.find_or_create_project("CLI")
    run_id = new_run(pid)
    assert f"Run {run_id} wrote no files." in invoke("workspace", "diff").text
    missing = invoke("workspace", "show", "nope.py")
    assert missing.exit_code == 1 and "No file nope.py" in missing.text


def test_workspace_show_names_a_binary_file():
    store.init_db()
    pid = store.find_or_create_project("CLI")
    (workspace.ensure(pid) / "logo.png").write_bytes(b"\x89PNG\x00\x01")
    assert "logo.png is binary" in invoke("workspace", "show", "logo.png").text


@needs_git
def test_workspace_push_to_the_saved_remote(tmp_path):
    store.init_db()
    pid = store.find_or_create_project("CLI")
    run_id = new_run(pid)
    workspace.write_files(pid, run_id, [("app.py", "print(1)\n")])
    assert invoke("workspace", "commit").exit_code == 0
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(workspace.root(pid), "remote", "add", "origin", str(remote))  # a local path, set by hand (the CLI only takes URLs)

    result = invoke("workspace", "push", "--yes")
    assert result.exit_code == 0, result.output
    assert f"Pushed juli/run-{run_id}" in result.text
    assert git(remote, "branch", "--list").stdout.strip() == f"juli/run-{run_id}"


def test_workspace_push_needs_a_remote():
    store.init_db()
    new_run(store.find_or_create_project("CLI"))
    result = invoke("workspace", "push")
    assert result.exit_code == 1 and "Say which remote to push to" in result.text


# ─── Models ──────────────────────────────────────────────────


def test_hugging_face_lookup(net, laptop):
    net.handler = serve(hf_routes(LLAMA_REPO, "hf_model_llama.json", "hf_tree_llama.json"))
    result = invoke("models", "hf", LLAMA_REPO)
    assert result.exit_code == 0, result.output
    assert "License:" in result.text and f"hf.co/{LLAMA_REPO}:Q4_K_M" in result.text


# ─── Dashboard build ─────────────────────────────────────────


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    folder = tmp_path / "frontend"
    folder.mkdir()
    monkeypatch.setattr(cli, "FRONTEND_DIR", folder)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "npm")
    return folder


def test_build_dashboard_installs_then_builds(frontend, monkeypatch):
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda argv, **kw: calls.append((argv, kw["cwd"])))
    cli.build_dashboard()
    assert calls == [(["npm", "install"], frontend), (["npm", "run", "build"], frontend)]
    (frontend / "node_modules").mkdir()
    calls.clear()
    cli.build_dashboard()
    assert calls == [(["npm", "run", "build"], frontend)]  # packages already there


def test_build_dashboard_failures_are_messages(frontend, monkeypatch, capsys):
    def fail(argv, **kw):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(cli.subprocess, "run", fail)
    with pytest.raises(cli.typer.Exit):
        cli.build_dashboard()
    assert "The dashboard build failed" in " ".join(capsys.readouterr().out.split())

    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    with pytest.raises(cli.typer.Exit):
        cli.build_dashboard()
    assert "Node.js is needed" in " ".join(capsys.readouterr().out.split())
