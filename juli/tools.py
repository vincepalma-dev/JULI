"""
The agents' built-in tools: their schemas, which roles get which, and the
read-only tools themselves.

Every tool works inside the project's workspace and goes through its path
guard. The read-only tools (list, read, search) run here; write_file,
run_command and handoff need the run (the bus, approvals, the crew), so the
engine runs them. MCP servers add more tools (juli.mcp).

Tool results are untrusted input: a file can say anything. They go back to
the model as tool messages and never change approvals, the sandbox, Privacy
Mode or keys.
"""

from dataclasses import dataclass

from juli import terminal, workspace

MAX_RESULT_CHARS = terminal.MAX_OUTPUT_CHARS
MAX_LISTED = 500
MAX_MATCHES = 100
MAX_READ_LINES = 400


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema of the arguments

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _object(required: tuple[str, ...] = (), **properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(required)}


_PATH = {"type": "string", "description": "A path relative to the project folder, e.g. src/app.py"}

BUILTIN = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "list_files",
            "List the project's files with their sizes, optionally only those under one folder.",
            _object(directory={"type": "string", "description": "A folder relative to the project folder; empty for all"}),
        ),
        ToolSpec(
            "read_file",
            f"Read a text file from the project, optionally a range of lines (at most {MAX_READ_LINES} lines per call).",
            _object(
                ("path",),
                path=_PATH,
                start_line={"type": "integer", "description": "First line to read, from 1"},
                end_line={"type": "integer", "description": "Last line to read"},
            ),
        ),
        ToolSpec(
            "search_files",
            f"Find lines containing some text (case-insensitive) in the project's text files. Shows up to {MAX_MATCHES} matches.",
            _object(
                ("text",),
                text={"type": "string", "description": "The text to look for"},
                path={"type": "string", "description": "Only search under this file or folder"},
            ),
        ),
        ToolSpec(
            "write_file",
            "Write a complete file in the project, creating or replacing it.",
            _object(("path", "content"), path=_PATH, content={"type": "string", "description": "The whole file"}),
        ),
        ToolSpec(
            "run_command",
            "Run one command in the project folder, such as the tests or a linter, and get its output. "
            "Test and lint commands may run on their own in the sandbox; anything else asks the user first.",
            _object(("command",), command={"type": "string", "description": "The command, e.g. pytest -q"}),
        ),
        ToolSpec(
            "handoff",
            "Hand work to a colleague in the crew, by name or role (for example a failing test to the coder). "
            "They take a turn with your reason; then you get their reply and carry on.",
            _object(
                ("to", "reason"),
                to={"type": "string", "description": "The colleague's name or role"},
                reason={"type": "string", "description": "What they should do, with the details they need"},
            ),
        ),
    )
}

READ = ("list_files", "read_file", "search_files")
WORK = (*READ, "write_file", "run_command", "handoff")

# Built-in tools by role, or by protocol for turns that aren't the role's own.
ROLE_TOOLS = {
    "planner": READ,
    "discuss": READ,
    "revise": READ,
    "follow_up": READ,
    "coder": WORK,
    "fix": WORK,
    "tester": WORK,
    "custom": WORK,
    "reviewer": (*READ, "run_command", "handoff"),
    "docs": (*READ, "write_file", "handoff"),
}

# Calls that change the workspace or hand work on. After one, repeating an
# earlier call is no longer a loop: its result may differ now.
CHANGES = ("write_file", "handoff")

# Added to the reply instructions of a turn that has tools.
PROTOCOL = (
    "You have tools to inspect the project folder (list_files, read_file, search_files); use them instead of guessing "
    "what is there. Where you have write_file and run_command, they do the same as file blocks and bash run blocks."
)


class ToolError(ValueError):
    """A tool call that can't be done; the message goes back to the model."""


def check_args(spec: dict, args: dict) -> str | None:
    """Why `args` don't fit the tool's schema, or None."""
    properties = spec.get("properties") or {}
    for name in spec.get("required") or []:
        if name not in args:
            return f"'{name}' is required"
    for name, value in args.items():
        expected = (properties.get(name) or {}).get("type")
        if expected == "string" and not isinstance(value, str):
            return f"'{name}' must be a string"
        if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            return f"'{name}' must be a whole number"
    return None


def cut(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + f"\n[cut at {MAX_RESULT_CHARS:,} characters]"


def _under(rel: str, folder: str) -> bool:
    return not folder or rel == folder or rel.startswith(folder + "/")


def run_read(project_id: str, name: str, args: dict) -> str:
    """Run one read-only tool. ToolError (or PathRefused) when it can't."""
    if name == "list_files":
        return list_files(project_id, args.get("directory") or "")
    if name == "read_file":
        return read_file(project_id, args["path"], args.get("start_line") or 1, args.get("end_line"))
    if name == "search_files":
        return search_files(project_id, args["text"], args.get("path") or "")
    raise ToolError(f"'{name}' isn't a read-only tool")


def list_files(project_id: str, directory: str = "") -> str:
    folder = workspace.clean_path(directory) if directory.strip(" ./") else ""
    files = [f for f in workspace.tree(project_id) if _under(f["path"], folder)]
    if not files:
        return f"No files under {folder}." if folder else "The project folder is empty."
    lines = [f"{f['path']}  ({f['size']:,} bytes)" for f in files[:MAX_LISTED]]
    if len(files) > MAX_LISTED:
        lines.append(f"(and {len(files) - MAX_LISTED:,} more; list a folder to see them)")
    return cut("\n".join(lines))


def read_file(project_id: str, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    try:
        found = workspace.read_file(project_id, path)
    except FileNotFoundError:
        raise ToolError(f"{path} doesn't exist") from None
    if found["content"] is None:
        raise ToolError(f"{found['path']} is {'binary' if found['binary'] else 'too large to read'}")
    lines = found["content"].splitlines()
    first = max(1, start_line)
    last = min(len(lines), end_line or first + MAX_READ_LINES - 1, first + MAX_READ_LINES - 1)
    if not lines:
        return f"{found['path']} is empty."
    if first > len(lines):
        raise ToolError(f"{found['path']} has only {len(lines)} lines")
    if last < first:
        raise ToolError("end_line is before start_line")
    header = f"{found['path']}, lines {first}-{last} of {len(lines)}:"
    return cut(header + "\n" + "\n".join(lines[first - 1 : last]))


def search_files(project_id: str, text: str, path: str = "") -> str:
    if not text.strip():
        raise ToolError("Say what text to look for")
    base = workspace.root(project_id)
    if not base.is_dir():
        return "The project folder is empty."
    folder = workspace.clean_path(path) if path.strip(" ./") else ""
    needle = text.lower()
    matches: list[str] = []
    for rel, file in workspace.walk(base, workspace.NOT_REVIEWED):
        if not _under(rel, folder) or file.stat().st_size > workspace.MAX_FILE_BYTES:
            continue
        try:
            content = file.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(content.splitlines(), 1):
            if needle in line.lower():
                matches.append(f"{rel}:{number}: {line.strip()[:200]}")
                if len(matches) >= MAX_MATCHES:
                    return cut("\n".join(matches) + f"\n(stopped at {MAX_MATCHES} matches)")
    return cut("\n".join(matches)) if matches else f"No matches for {text!r}."
