"""
The artifact workspace: data/workspace/<project_id>/ is a project's working
tree and its own git repo.

Fenced blocks that name a path (```python path=src/app.py) become files.
Every path goes through the guard first: it must resolve inside the
workspace, so absolute paths, drive letters, "..", .git and symlinks that
point outside are refused. Each run stores the before-image of every file it
writes, for diffs.

Git runs through subprocess with argument lists, pinned to the workspace's
own repo (--git-dir and --work-tree, no GIT_* variables from the host) with
hooks and fsmonitor off, so it never touches the user's current folder and
never runs code from the workspace. Runs commit to branch juli/run-<id>.
"""

import difflib
import io
import logging
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

from juli import config, store

log = logging.getLogger(__name__)

PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_PATH = 400
MAX_FILE_BYTES = 1_000_000
MAX_FILES_PER_TURN = 200
MAX_TREE_FILES = 5000
MAX_REVIEW_CHARS = 200_000
GIT_TIMEOUT = 60
PUSH_TIMEOUT = 120

# A fenced block: an opening fence of 3+ backticks or tildes with an info
# string, the body, then the same fence on its own line.
FENCE = re.compile(r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^\n]*)\n(?P<body>.*?)^(?P=fence)[ \t]*$", re.MULTILINE | re.DOTALL)
PATH_ATTR = re.compile(r"""(?:^|\s)path=(?:"([^"]+)"|'([^']+)'|(\S+))""")
RUN_INFO = re.compile(r"^(?:bash|sh|shell|console)\s+run(?:\s|$)", re.IGNORECASE)

WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
SHORT_NAME = re.compile(r"~\d")  # 8.3 aliases such as GIT~1 can name .git on Windows
# Skipped when the workspace is shown to the reviewer.
NOT_REVIEWED = {"__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build"}

# A remote to push to: https, ssh, or scp-style git@host:path.
REMOTE = re.compile(r"^(?:https://|ssh://)[^\s]+$|^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s]+$")


class PathRefused(ValueError):
    """A file path from an agent that may not be written."""


class GitError(RuntimeError):
    """A git step failed; the message says why."""


# ─── Extraction ──────────────────────────────────────────────


def _blocks(text: str) -> Iterator[tuple[str, str]]:
    for m in FENCE.finditer(text):
        yield m.group("info").strip(), m.group("body")


def extract_files(text: str) -> list[tuple[str, str]]:
    """(path, content) for each fenced block that names a path. A later block for the same path wins."""
    files: dict[str, str] = {}
    for info, body in _blocks(text):
        m = PATH_ATTR.search(info)
        if m:
            files[next(g for g in m.groups() if g)] = body
    return list(files.items())


def extract_commands(text: str) -> list[str]:
    """The commands in ```bash run blocks, one per block, in order."""
    return [body.strip() for info, body in _blocks(text) if RUN_INFO.match(info) and body.strip()]


# ─── The path guard ──────────────────────────────────────────


def root(project_id: str) -> Path:
    """A project's workspace folder (not created)."""
    if not PROJECT_ID.match(project_id):
        raise ValueError("Not a valid project id")
    return config.data_dir() / "workspace" / project_id


def clean_path(rel: str) -> str:
    """A relative path from an agent, normalised to a/b/c, or PathRefused."""
    if not rel or len(rel) > MAX_PATH or "\0" in rel:
        raise PathRefused("not a valid path")
    posix = rel.replace("\\", "/")
    if posix.startswith("/") or re.match(r"^[A-Za-z]:", posix):
        raise PathRefused("absolute paths aren't allowed")
    parts = [p for p in posix.split("/") if p not in ("", ".")]
    if not parts:
        raise PathRefused("not a valid path")
    for part in parts:
        if part == "..":
            raise PathRefused("'..' isn't allowed")
        if part.lower().rstrip(". ") == ".git" or SHORT_NAME.search(part):
            raise PathRefused("the .git folder is off limits")
        if ":" in part or part != part.rstrip(". ") or part.split(".")[0].lower() in WINDOWS_RESERVED:
            raise PathRefused(f"'{part}' isn't a portable file name")
    return "/".join(parts)


def resolve(base: Path, rel: str) -> Path:
    """The path of `rel` (already cleaned) inside `base`. Refused if it
    resolves outside, e.g. through a symlink, or into .git."""
    base = base.resolve()
    target = base.joinpath(*rel.split("/"))
    resolved = target.resolve()
    try:
        inside = resolved.relative_to(base)
    except ValueError:
        raise PathRefused("it leaves the workspace") from None
    if any(part.lower() == ".git" for part in inside.parts):
        raise PathRefused("the .git folder is off limits")
    return target


# ─── Files ───────────────────────────────────────────────────


def ensure(project_id: str) -> Path:
    """The workspace folder, created with its git repo if needed. Without git,
    files still work; only commits don't."""
    path = root(project_id)
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists() and shutil.which("git"):
        try:
            result = subprocess.run(["git", "init", "-q", str(path)], check=False, **_git_kwargs(path))
        except subprocess.TimeoutExpired:
            log.warning("git init timed out in %s", path)
        else:
            if result.returncode != 0:
                log.warning("git init failed in %s: %s", path, result.stderr.strip())
    return path


def write_files(project_id: str, run_id: int, files: list[tuple[str, str]]) -> tuple[list[str], list[tuple[str, str]]]:
    """Write an agent's files. Returns (paths written, [(path, why refused)])."""
    base = ensure(project_id)
    written: list[str] = []
    refused: list[tuple[str, str]] = [(rel, "too many files in one reply") for rel, _ in files[MAX_FILES_PER_TURN:]]
    for rel, content in files[:MAX_FILES_PER_TURN]:
        try:
            clean = clean_path(rel)
            path = resolve(base, clean)
            data = content.encode("utf-8")
            if len(data) > MAX_FILE_BYTES:
                raise PathRefused(f"it's over {MAX_FILE_BYTES // 1_000_000} MB")
            if path.is_symlink() or path.is_dir():
                raise PathRefused("a link or folder is in the way")
            before = None
            if path.exists():
                try:
                    before = path.read_bytes().decode("utf-8")
                except UnicodeDecodeError:
                    raise PathRefused("the existing file isn't text") from None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except PathRefused as e:
            refused.append((rel, str(e)))
            continue
        except OSError as e:
            refused.append((rel, e.strerror or "it couldn't be written"))
            continue
        store.record_file(run_id, clean, before, content)
        written.append(clean)
    return written, refused


def _is_link(path: Path) -> bool:
    """A symlink, or a Windows junction (which islink() misses on Python 3.10)."""
    return path.is_symlink() or os.path.normcase(path.resolve()) != os.path.normcase(path.absolute())


def _walk(base: Path, skip: set[str] | frozenset[str] = frozenset()) -> Iterator[tuple[str, Path]]:
    """(relative path, path) of every regular file, skipping .git and links."""
    base = base.resolve()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d.lower() != ".git" and d not in skip and not _is_link(Path(dirpath, d)))
        for name in sorted(filenames):
            path = Path(dirpath, name)
            if path.is_file() and not _is_link(path):
                yield path.relative_to(base).as_posix(), path


def tree(project_id: str) -> list[dict]:
    """Every file in the workspace (except .git), with its size."""
    base = root(project_id)
    if not base.is_dir():
        return []
    files = []
    for rel, path in _walk(base):
        files.append({"path": rel, "size": path.stat().st_size})
        if len(files) >= MAX_TREE_FILES:
            break
    return files


def read_file(project_id: str, rel: str) -> dict:
    """One file's content; binary files come back without it. FileNotFoundError if missing."""
    clean = clean_path(rel)
    path = resolve(root(project_id), clean)
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(clean)
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        return {"path": clean, "size": size, "binary": False, "too_large": True, "content": None}
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return {"path": clean, "size": size, "binary": True, "too_large": False, "content": None}
    return {"path": clean, "size": size, "binary": False, "too_large": False, "content": content}


def _lines(text: str | None) -> list[str]:
    lines = (text or "").splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def diff(run_id: int) -> str:
    """A unified diff of every file the run wrote, from before the run to its last write."""
    parts: list[str] = []
    for f in store.run_files(run_id):
        before = f["before_text"]
        parts.extend(
            difflib.unified_diff(
                _lines(before),
                _lines(f["after_text"]),
                fromfile="/dev/null" if before is None else f"a/{f['path']}",
                tofile=f"b/{f['path']}",
            )
        )
    return "".join(parts)


def zip_tree(project_id: str) -> bytes:
    """The workspace as a zip archive, without .git and links."""
    buffer = io.BytesIO()
    base = root(project_id)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if base.is_dir():
            for rel, path in _walk(base):
                zf.write(path, rel)
    return buffer.getvalue()


def review_text(project_id: str) -> str:
    """The workspace's text files as path-labelled code blocks, for the reviewer. Empty if there are none."""
    base = root(project_id)
    if not base.is_dir():
        return ""
    parts: list[str] = []
    total = 0
    for rel, path in _walk(base, NOT_REVIEWED):
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            content = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        longest = max((len(m) for m in re.findall(r"`{3,}", content)), default=2)
        fence = "`" * (longest + 1)
        block = f"{fence} path={rel}\n{content}{'' if content.endswith(chr(10)) else chr(10)}{fence}"
        if total + len(block) > MAX_REVIEW_CHARS:
            parts.append(f"(More files are in the workspace; they didn't fit in {MAX_REVIEW_CHARS:,} characters.)")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


# ─── Git ─────────────────────────────────────────────────────


def _git_kwargs(cwd: Path, timeout: int = GIT_TIMEOUT) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "JULI_TOKEN"}
    env["GIT_TERMINAL_PROMPT"] = "0"  # fail instead of waiting for a password nobody can type
    return {
        "cwd": cwd,
        "env": env,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }


def _git(base: Path, *args: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    argv = [
        "git",
        f"--git-dir={base / '.git'}",
        f"--work-tree={base}",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        *args,
    ]
    try:
        return subprocess.run(argv, check=False, **_git_kwargs(base, timeout))
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} took longer than {timeout} s") from None


def _check(result: subprocess.CompletedProcess, step: str) -> str:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise GitError(f"{step} failed: {detail[-1] if detail else f'exit code {result.returncode}'}")
    return (result.stdout or "").strip()


def _repo(project_id: str) -> Path:
    if not shutil.which("git"):
        raise GitError("git isn't installed")
    base = ensure(project_id)
    if not (base / ".git").is_dir():
        raise GitError("The workspace has no git repo")
    return base


def branch_name(run_id: int) -> str:
    return f"juli/run-{run_id}"


def _branch_exists(base: Path, branch: str) -> bool:
    return _git(base, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def commit(project_id: str, run_id: int, message: str) -> dict:
    """Commit the whole workspace to branch juli/run-<id>. An existing branch
    is never reset, and another run's branch is only switched to when that
    leaves the workspace exactly as it is."""
    base = _repo(project_id)
    branch = branch_name(run_id)
    if _branch_exists(base, branch):
        current = _git(base, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
        if current != branch:
            on = f" on {current}" if current else ""
            if _git(base, "rev-parse", "--verify", "--quiet", "HEAD").returncode != 0:
                # An unborn branch (e.g. made with --orphan in the terminal): there's no run to commit.
                raise GitError(
                    f"{current or 'HEAD'} has no commits yet, so switching to {branch} could overwrite "
                    f"the workspace's files. In the terminal, commit them on {current or 'a branch'} "
                    f"or run `git switch {branch}` yourself, then try again."
                )
            if _check(_git(base, "status", "--porcelain"), "git status"):
                raise GitError(f"The workspace has uncommitted later work{on}. Commit the latest run first, then commit {branch}.")
            if _git(base, "diff", "--quiet", "HEAD", branch).returncode != 0:
                raise GitError(
                    f"Switching to {branch} would change the workspace, which holds later work{on}. Commit the latest run first."
                )
            _check(_git(base, "switch", "-q", branch), f"Switching to {branch}")
    else:
        _check(_git(base, "switch", "-q", "-c", branch), f"Creating {branch}")
    _check(_git(base, "add", "-A"), "git add")
    if not _check(_git(base, "status", "--porcelain"), "git status"):
        return {"branch": branch, "commit": None, "detail": "Nothing to commit"}
    identity: list[str] = []
    if _git(base, "config", "user.email").returncode != 0:
        identity = ["-c", "user.name=JULI", "-c", "user.email=juli@localhost"]
    _check(_git(base, *identity, "commit", "-q", "-m", message), "git commit")
    sha = _check(_git(base, "rev-parse", "HEAD"), "git rev-parse")
    return {"branch": branch, "commit": sha, "detail": f"Committed to {branch}"}


def remote_problem(url: str) -> str | None:
    """Why a push remote isn't accepted, or None."""
    if url.startswith("-") or not REMOTE.match(url):
        return "Use an https://, ssh:// or git@host:path remote"
    if url.startswith("https://") and urlparse(url).password:
        return "Don't put a password or token in the URL; git's credential helper keeps it"
    return None


def current_remote(project_id: str) -> str | None:
    base = _repo(project_id)
    result = _git(base, "remote", "get-url", "origin")
    return result.stdout.strip() if result.returncode == 0 else None


def push(project_id: str, run_id: int, remote: str | None = None) -> dict:
    """Push branch juli/run-<id> to `remote` (saved as origin) or the saved origin."""
    base = _repo(project_id)
    branch = branch_name(run_id)
    if not _branch_exists(base, branch):
        raise GitError(f"Commit run {run_id} first: {branch} doesn't exist")
    if remote:
        problem = remote_problem(remote)
        if problem:
            raise GitError(problem)
        verb = "set-url" if current_remote(project_id) else "add"
        _check(_git(base, "remote", verb, "origin", remote), "Saving the remote")
    elif not current_remote(project_id):
        raise GitError("Say which remote to push to")
    ref = f"refs/heads/{branch}"
    _check(_git(base, "push", "origin", f"{ref}:{ref}", timeout=PUSH_TIMEOUT), "git push")
    return {"branch": branch, "remote": current_remote(project_id), "detail": f"Pushed {branch}"}
