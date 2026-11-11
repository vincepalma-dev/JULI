import io
import os
import shutil
import subprocess
import zipfile

import pytest
from typer.testing import CliRunner

from juli import cli, config, engine, store, workspace
from juli.workspace import PathRefused

from .conftest import AUTH, docker_up

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git isn't installed")


@pytest.fixture
def project():
    store.init_db()
    return store.create_project("ws")["id"]


def new_run(project_id, prompt="Build it"):
    return store.create_run(project_id, prompt, "code")


def git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False)


# ─── Extraction ──────────────────────────────────────────────


def test_extract_files_from_path_labelled_blocks():
    text = (
        "Here you go.\n\n"
        "```python path=src/app.py\nprint('hi')\n```\n\n"
        "```text\nno path, not a file\n```\n\n"
        '```js path="web/main.js"\nconsole.log(1)\n```\n\n'
        "~~~~markdown path=README.md\nA ``` fence inside\n~~~~\n\n"
        "```python path=src/app.py\nprint('second wins')\n```\n"
    )
    assert workspace.extract_files(text) == [
        ("src/app.py", "print('second wins')\n"),
        ("web/main.js", "console.log(1)\n"),
        ("README.md", "A ``` fence inside\n"),
    ]


def test_extract_commands_from_run_blocks():
    text = "```bash run\npytest -q\n```\n```bash\nnot run\n```\n```sh run\nnpm test\n```\n```bash run\n\n```"
    assert workspace.extract_commands(text) == ["pytest -q", "npm test"]


# ─── The path guard ──────────────────────────────────────────


@pytest.mark.parametrize(
    "rel",
    [
        "",
        "/etc/passwd",
        "\\\\server\\share\\x",
        "C:\\Windows\\x.py",
        "c:x.py",
        "../escape.py",
        "src/../../escape.py",
        ".git/hooks/pre-commit",
        "src/.GIT/config",
        ".git./config",
        "GIT~1/config",
        "con.txt",
        "src/aux",
        "file.txt:stream",
        "trailing.",
        "nul\0byte",
        "a/" * 250 + "b",
    ],
)
def test_clean_path_refuses(rel):
    with pytest.raises(PathRefused):
        workspace.clean_path(rel)


@pytest.mark.parametrize(
    "rel, clean",
    [
        ("src/app.py", "src/app.py"),
        ("./src//app.py", "src/app.py"),
        ("src\\win\\x.py", "src/win/x.py"),
        (".gitignore", ".gitignore"),
        (".github/workflows/ci.yml", ".github/workflows/ci.yml"),
        ("console.py", "console.py"),
    ],
)
def test_clean_path_accepts(rel, clean):
    assert workspace.clean_path(rel) == clean


def test_symlink_pointing_outside_is_refused(project, tmp_path):
    base = workspace.ensure(project)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("not yours", encoding="utf-8")
    try:
        os.symlink(outside, base / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("this machine can't create symlinks")
        import _winapi  # a directory junction needs no special rights on Windows

        _winapi.CreateJunction(str(outside), str(base / "link"))
    run_id = new_run(project)
    written, refused = workspace.write_files(project, run_id, [("link/evil.py", "x"), ("ok.py", "y")])
    assert written == ["ok.py"]
    assert refused == [("link/evil.py", "it leaves the workspace")]
    assert not (outside / "evil.py").exists()
    # Links aren't followed when listing, zipping or reviewing.
    assert [f["path"] for f in workspace.tree(project)] == ["ok.py"]
    assert zipfile.ZipFile(io.BytesIO(workspace.zip_tree(project))).namelist() == ["ok.py"]
    assert "not yours" not in workspace.review_text(project)
    with pytest.raises(PathRefused):
        workspace.read_file(project, "link/private.txt")


def test_project_id_must_be_plain():
    with pytest.raises(ValueError):
        workspace.root("../other")


# ─── Files ───────────────────────────────────────────────────


def test_write_files_keeps_the_first_before_image(project):
    base = workspace.ensure(project)
    (base / "app.py").write_bytes(b"old\n")
    run_id = new_run(project)
    workspace.write_files(project, run_id, [("app.py", "new\n"), ("lib/util.py", "u = 1\n")])
    workspace.write_files(project, run_id, [("app.py", "newer\n")])
    files = {f["path"]: f for f in store.run_files(run_id)}
    assert files["app.py"]["before_text"] == "old\n" and files["app.py"]["after_text"] == "newer\n"
    assert files["lib/util.py"]["before_text"] is None
    assert (base / "app.py").read_bytes() == b"newer\n"


def test_write_files_refuses_binary_files_and_oversized_content(project, monkeypatch):
    base = workspace.ensure(project)
    (base / "logo.png").write_bytes(b"\x89PNG\xff\xfe")
    monkeypatch.setattr(workspace, "MAX_FILE_BYTES", 10)
    written, refused = workspace.write_files(project, new_run(project), [("logo.png", "x"), ("big.txt", "x" * 11)])
    assert written == []
    assert [why for _, why in refused] == ["the existing file isn't text", "it's over 0 MB"]
    assert (base / "logo.png").read_bytes() == b"\x89PNG\xff\xfe"


def test_tree_read_and_zip_skip_git(project):
    base = workspace.ensure(project)
    (base / ".git").mkdir(exist_ok=True)
    (base / ".git" / "config").write_text("secret", encoding="utf-8")
    workspace.write_files(project, new_run(project), [("src/app.py", "print(1)\n")])
    (base / "img.bin").write_bytes(b"\xff\x00")

    assert [f["path"] for f in workspace.tree(project)] == ["img.bin", "src/app.py"]
    assert workspace.read_file(project, "src/app.py")["content"] == "print(1)\n"
    assert workspace.read_file(project, "img.bin")["binary"] is True
    with pytest.raises(FileNotFoundError):
        workspace.read_file(project, "missing.py")
    with pytest.raises(PathRefused):
        workspace.read_file(project, ".git/config")
    names = zipfile.ZipFile(io.BytesIO(workspace.zip_tree(project))).namelist()
    assert sorted(names) == ["img.bin", "src/app.py"]


def test_diff_shows_new_and_changed_files(project):
    base = workspace.ensure(project)
    (base / "app.py").write_bytes(b"a = 1\nb = 2\n")
    run_id = new_run(project)
    workspace.write_files(project, run_id, [("app.py", "a = 1\nb = 3\n"), ("new.py", "x = 1")])
    diff = workspace.diff(run_id)
    assert "--- a/app.py\n+++ b/app.py\n" in diff and "-b = 2\n+b = 3\n" in diff
    assert "--- /dev/null\n+++ b/new.py\n" in diff and "\\ No newline at end of file" in diff


def test_review_mode_reads_the_workspace_files(project):
    run_id = new_run(project)
    store.save_message(project, run_id, {"agent_name": "Coder", "content": "old output"})
    assert "old output" in engine.review_source(project)
    workspace.write_files(project, run_id, [("app.py", "print('x')\n"), ("__pycache__/app.pyc", "junk")])
    source = engine.review_source(project)
    assert "``` path=app.py\nprint('x')\n```" in source
    assert "old output" not in source and "pyc" not in source


# ─── Git ─────────────────────────────────────────────────────


@needs_git
def test_commit_goes_to_the_run_branch_in_the_workspace_repo_only(project, tmp_path, monkeypatch):
    # The user's folder is a repo too, and GIT_DIR points at it: neither may be touched.
    git(tmp_path, "init", "-q")
    monkeypatch.setenv("GIT_DIR", str(tmp_path / ".git"))
    run_id = new_run(project, "Build a todo app\nwith details")
    workspace.write_files(project, run_id, [("app.py", "print(1)\n")])

    result = workspace.commit(project, run_id, f"JULI run {run_id}: Build a todo app")
    base = workspace.root(project)
    assert result["branch"] == f"juli/run-{run_id}" and result["commit"]
    assert git(base, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == f"juli/run-{run_id}"
    assert git(base, "log", "-1", "--format=%s").stdout.strip() == f"JULI run {run_id}: Build a todo app"
    assert git(base, "ls-files").stdout.split() == ["app.py"]
    assert git(tmp_path, "rev-parse", "--verify", "HEAD").returncode != 0  # no commit in the outer repo
    assert git(tmp_path, "status", "--porcelain").stdout.strip() in ("", "?? data/")

    assert workspace.commit(project, run_id, "again")["commit"] is None  # nothing new


@needs_git
def test_an_existing_run_branch_is_never_reset(project):
    first, second = new_run(project), new_run(project)
    workspace.write_files(project, first, [("a.py", "a\n")])
    sha1 = workspace.commit(project, first, "first")["commit"]
    workspace.write_files(project, second, [("b.py", "b\n")])
    workspace.commit(project, second, "second")
    base = workspace.root(project)
    assert git(base, "rev-parse", f"juli/run-{first}").stdout.strip() == sha1


@needs_git
def test_an_older_run_branch_is_not_switched_to_over_later_work(project):
    first, second = new_run(project), new_run(project)
    workspace.write_files(project, first, [("a.py", "a\n")])
    sha1 = workspace.commit(project, first, "first")["commit"]
    workspace.write_files(project, second, [("b.py", "b\n")])
    workspace.commit(project, second, "second")
    base = workspace.root(project)

    # Committed later work on juli/run-<second>: switching back would change the files.
    with pytest.raises(workspace.GitError, match=f"later work on juli/run-{second}. Commit the latest run first"):
        workspace.commit(project, first, "again")
    assert git(base, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == f"juli/run-{second}"
    assert git(base, "rev-parse", f"juli/run-{first}").stdout.strip() == sha1
    assert (base / "b.py").exists()

    # Uncommitted later work: refused too, and it stays where it is.
    workspace.write_files(project, second, [("b.py", "b2\n")])
    with pytest.raises(workspace.GitError, match=f"uncommitted later work on juli/run-{second}. Commit the latest run first"):
        workspace.commit(project, first, "again")
    assert git(base, "rev-parse", f"juli/run-{first}").stdout.strip() == sha1
    assert (base / "b.py").read_bytes() == b"b2\n"

    # The checked-out branch still commits as before.
    assert workspace.commit(project, second, "second again")["commit"]


@needs_git
def test_an_unborn_branch_is_not_mistaken_for_an_uncommitted_run(project):
    run_id = new_run(project)
    workspace.write_files(project, run_id, [("a.py", "a\n")])
    workspace.commit(project, run_id, "first")
    base = workspace.root(project)
    git(base, "checkout", "-q", "--orphan", "scratch")  # e.g. done by hand in the terminal

    with pytest.raises(workspace.GitError) as exc:
        workspace.commit(project, run_id, "again")
    message = str(exc.value)
    assert "scratch has no commits yet" in message and f"git switch juli/run-{run_id}" in message
    assert "Commit the latest run" not in message
    assert git(base, "symbolic-ref", "--short", "HEAD").stdout.strip() == "scratch"
    assert (base / "a.py").read_bytes() == b"a\n"


@needs_git
def test_switching_to_an_identical_run_branch_is_allowed(project):
    run_id = new_run(project)
    workspace.write_files(project, run_id, [("a.py", "a\n")])
    workspace.commit(project, run_id, "first")
    base = workspace.root(project)
    git(base, "switch", "-q", "-c", "elsewhere")  # same tree, another branch
    assert workspace.commit(project, run_id, "again")["commit"] is None
    assert git(base, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == f"juli/run-{run_id}"


@needs_git
def test_workspace_hooks_never_run(project):
    base = workspace.ensure(project)
    hook = base / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\necho ran > '{(base / 'hook-ran').as_posix()}'\n", encoding="utf-8")
    hook.chmod(0o755)
    run_id = new_run(project)
    workspace.write_files(project, run_id, [("app.py", "x\n")])
    workspace.commit(project, run_id, "msg")
    assert not (base / "hook-ran").exists()


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://github.com/me/app.git", True),
        ("git@github.com:me/app.git", True),
        ("ssh://git@host/me/app.git", True),
        ("https://user:pw@github.com/me/app.git", False),
        ("-oProxyCommand=evil", False),
        ("ext::sh -c evil", False),
        ("file:///etc", False),
        ("/local/path", False),
    ],
)
def test_remote_problem(url, ok):
    assert (workspace.remote_problem(url) is None) == ok


@needs_git
def test_push_needs_a_commit_first(project):
    with pytest.raises(workspace.GitError, match="Commit run"):
        workspace.push(project, new_run(project), "https://github.com/me/app.git")


# ─── Routes ──────────────────────────────────────────────────


def test_workspace_routes(client):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = new_run(pid)
    workspace.write_files(pid, run_id, [("src/app.py", "print(1)\n")])

    assert client.get(f"/api/projects/{pid}/workspace/tree", headers=AUTH).json()["files"] == [{"path": "src/app.py", "size": 9}]
    r = client.get(f"/api/projects/{pid}/workspace/file", params={"path": "src/app.py"}, headers=AUTH)
    assert r.json()["content"] == "print(1)\n"
    assert client.get(f"/api/projects/{pid}/workspace/file", params={"path": "../x"}, headers=AUTH).status_code == 422
    assert client.get(f"/api/projects/{pid}/workspace/file", params={"path": "nope.py"}, headers=AUTH).status_code == 404
    r = client.get(f"/api/projects/{pid}/workspace/zip", headers=AUTH)
    assert r.headers["content-type"] == "application/zip" and "attachment" in r.headers["content-disposition"]
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == ["src/app.py"]
    assert client.get(f"/api/runs/{run_id}/files", headers=AUTH).json() == [{"path": "src/app.py", "status": "added"}]
    assert "+print(1)" in client.get(f"/api/runs/{run_id}/diff", headers=AUTH).json()["diff"]
    assert client.get("/api/projects/nope/workspace/tree", headers=AUTH).status_code == 404
    assert client.get("/api/runs/999/diff", headers=AUTH).status_code == 404


@needs_git
def test_commit_and_push_routes(client):
    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = new_run(pid)
    workspace.write_files(pid, run_id, [("app.py", "x\n")])
    r = client.post(f"/api/runs/{run_id}/commit", headers=AUTH)
    assert r.status_code == 200 and r.json()["branch"] == f"juli/run-{run_id}"

    # Pushing asks first: without confirm nothing is pushed.
    r = client.post(f"/api/runs/{run_id}/push", json={"remote": "https://github.com/me/app.git"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["detail"]["confirm"] == {"branch": f"juli/run-{run_id}", "remote": "https://github.com/me/app.git"}
    assert workspace.current_remote(pid) is None
    r = client.post(f"/api/runs/{run_id}/push", json={"remote": "https://user:pw@github.com/me/a.git", "confirm": True}, headers=AUTH)
    assert r.status_code == 422
    r = client.post(f"/api/runs/{run_id}/push", json={"confirm": True}, headers=AUTH)
    assert r.status_code == 409 and "remote" in r.json()["detail"]


def cli_run(*args, **kwargs):
    result = CliRunner().invoke(cli.app, list(args), **kwargs)
    result.text = " ".join(result.output.split())
    return result


@needs_git
def test_cli_workspace_commands(tmp_path):
    store.init_db()
    pid = store.find_or_create_project("CLI")
    run_id = new_run(pid, "Make an app")
    workspace.write_files(pid, run_id, [("src/app.py", "print(1)\n")])

    assert "src/app.py" in cli_run("workspace", "tree").text
    assert cli_run("workspace", "show", "src/app.py").output == "print(1)\n"
    assert cli_run("workspace", "show", "../x").exit_code == 1
    assert "+print(1)" in cli_run("workspace", "diff").output
    out = tmp_path / "ws.zip"
    assert cli_run("workspace", "zip", str(out)).exit_code == 0
    assert zipfile.ZipFile(out).namelist() == ["src/app.py"]
    assert f"Committed to juli/run-{run_id}" in cli_run("workspace", "commit").text
    assert cli_run("workspace", "commit", "--run", "999").exit_code == 1

    # Push asks first; saying no pushes nothing and saves no remote.
    result = cli_run("workspace", "push", "--remote", "https://github.com/me/app.git", input="n\n")
    assert result.exit_code == 1 and f"Push juli/run-{run_id} to https://github.com/me/app.git?" in result.text
    assert workspace.current_remote(pid) is None
    assert "password or token" in cli_run("workspace", "push", "--remote", "https://user:pw@github.com/a/b").text


def test_cli_sandbox(procs):
    assert "Sandbox: off" in cli_run("sandbox").text
    procs.handler = docker_up()
    result = cli_run("sandbox", "on", "--image", "ghcr.io/me/tools:1", "--timeout", "60")
    assert "Sandbox: on · image ghcr.io/me/tools:1 · timeout 60 s" in result.text
    assert config.load_settings()["sandbox"]["enabled"] is True
    assert cli_run("sandbox", "on", "--image", "--bad").exit_code != 0
    assert cli_run("sandbox", "maybe").exit_code == 1
    assert "Sandbox: off" in cli_run("sandbox", "off").text


def test_commit_refused_while_a_task_runs_in_the_project(client):
    from juli.bus import message_bus

    pid = client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]
    run_id = new_run(pid)
    assert message_bus.try_begin_task("t", pid)
    assert client.post(f"/api/runs/{run_id}/commit", headers=AUTH).status_code == 409


@pytest.mark.parametrize(
    ("rel", "why"),
    [
        ("/etc/passwd", "absolute paths aren't allowed"),
        ("C:/Windows/x.py", "absolute paths aren't allowed"),
        ("./", "not a valid path"),
        ("a\0b.py", "not a valid path"),
        (".git/config", "the .git folder is off limits"),
        ("src/.GIT/hooks/pre-commit", "the .git folder is off limits"),
    ],
)
def test_unsafe_paths_are_refused(project, rel, why):
    written, refused = workspace.write_files(project, new_run(project), [(rel, "x")])
    assert written == [] and refused == [(rel, why)]


def test_files_that_cant_be_written_safely_are_refused(project):
    base = workspace.ensure(project)
    (base / "logo.png").write_bytes(b"\x89PNG\xff\xfe")
    (base / "src").mkdir()
    run_id = new_run(project)
    big = "x" * (workspace.MAX_FILE_BYTES + 1)  # the limit is 1 MB
    written, refused = workspace.write_files(project, run_id, [("big.py", big), ("src", "x"), ("logo.png", "x"), ("ok.py", "x")])
    assert written == ["ok.py"]
    assert dict(refused) == {
        "big.py": "it's over 1 MB",
        "src": "a link or folder is in the way",
        "logo.png": "the existing file isn't text",
    }
    assert (base / "logo.png").read_bytes() == b"\x89PNG\xff\xfe"  # left as it was


def test_git_problems_are_git_errors(project, monkeypatch):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(workspace.subprocess, "run", slow)
    with pytest.raises(workspace.GitError, match="took longer than"):
        workspace._git(workspace.root(project), "status")
    failed = subprocess.CompletedProcess(["git"], 128, "", "fatal: not a git repository\n")
    with pytest.raises(workspace.GitError, match="git status failed: fatal: not a git repository"):
        workspace._check(failed, "git status")
    with pytest.raises(workspace.GitError, match="exit code 1"):
        workspace._check(subprocess.CompletedProcess(["git"], 1, "", ""), "git push")
    monkeypatch.setattr(workspace.shutil, "which", lambda name: None)
    with pytest.raises(workspace.GitError, match="git isn't installed"):
        workspace.commit(project, new_run(project), "m")
