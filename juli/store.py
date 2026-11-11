"""
SQLite store (WAL): projects, runs, messages, benchmarks, run_files.

Each task gets its own run row, so history is never deleted when a new task
starts. Deleting a project cascades to its runs and messages. A running run
keeps a checkpoint (JSON) in its row, so it can resume after a restart.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from juli import config


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """A connection that commits on success and is always closed."""
    conn = sqlite3.connect(config.db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


# Columns added to `messages` after the first schema; added in place on old DBs.
_MESSAGE_COLUMNS = {
    "run_id": "INTEGER REFERENCES runs(id) ON DELETE CASCADE",
    "model": "TEXT",
    "tokens_in": "INTEGER",
    "tokens_out": "INTEGER",
    "cost_usd": "REAL",
    "data": "TEXT",  # JSON: a decision's options, a command's result, ...
}

# Columns added to `runs` after the first schema.
_RUN_COLUMNS = {
    "checkpoint": "TEXT",  # the engine's run state after its latest step; NULL once complete or stopped
}

# Every runs column but the (large) checkpoint.
RUN_FIELDS = "id, project_id, prompt, mode, status, crew_json, tokens_in, tokens_out, cost_usd, started_at, ended_at"

# Runs with a checkpoint in these states can resume: interrupted (still
# "running" or "paused" after a restart) or ended by an error.
RESUMABLE = ("running", "paused", "error")


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                crew_json TEXT,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                ended_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                agent_name TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                message_type TEXT NOT NULL
            )
        """)
        for table, columns in (("messages", _MESSAGE_COLUMNS), ("runs", _RUN_COLUMNS)):
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, decl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        # The files each run wrote in its project's workspace, with their
        # content before the run first touched them (NULL: the run created it).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_files (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                before_text TEXT,
                after_text TEXT NOT NULL,
                PRIMARY KEY (run_id, path)
            )
        """)
        # The latest measured speed of each model on each machine.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                model_ref TEXT NOT NULL,
                tok_per_sec REAL NOT NULL,
                prefill_tok_per_sec REAL,
                hw_fingerprint TEXT NOT NULL,
                measured_at TEXT NOT NULL,
                PRIMARY KEY (model_ref, hw_fingerprint)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, id)")


# ─── Projects ────────────────────────────────────────────────


def get_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]


def create_project(name: str) -> dict:
    ts = now()
    project = {"id": str(uuid.uuid4()), "name": name, "created_at": ts, "updated_at": ts}
    with connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (project["id"], name, ts, ts),
        )
    return project


def project_exists(project_id: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is not None


def _load_data(raw: str | None) -> dict | None:
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def get_project(project_id: str) -> dict | None:
    """Project metadata with its full message history across all runs."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        project = dict(row)
        msg_rows = conn.execute(
            "SELECT run_id, agent_name, content, timestamp, message_type, model, tokens_in, tokens_out, cost_usd, data "
            "FROM messages WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        project["messages"] = [{**dict(mr), "data": _load_data(mr["data"])} for mr in msg_rows]
        return project


def delete_project(project_id: str) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0


# ─── Runs ────────────────────────────────────────────────────


def find_or_create_project(name: str) -> str:
    """The id of the most recently updated project with this name, created if missing."""
    with connect() as conn:
        row = conn.execute("SELECT id FROM projects WHERE name = ? ORDER BY updated_at DESC LIMIT 1", (name,)).fetchone()
    return row["id"] if row else create_project(name)["id"]


def create_run(project_id: str, prompt: str, mode: str, crew_json: str | None = None) -> int:
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (project_id, prompt, mode, status, crew_json, started_at) VALUES (?, ?, ?, 'running', ?, ?)",
            (project_id, prompt, mode, crew_json, ts),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
        return int(cur.lastrowid or 0)


def finish_run(run_id: int, status: str, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0) -> None:
    """End a run. Its checkpoint is kept only if it can still resume (an error)."""
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, tokens_in = ?, tokens_out = ?, cost_usd = ?, ended_at = ?, "
            "checkpoint = CASE WHEN ? IN ('complete', 'stopped') THEN NULL ELSE checkpoint END WHERE id = ?",
            (status, tokens_in, tokens_out, cost_usd, now(), status, run_id),
        )


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {RUN_FIELDS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def save_checkpoint(run_id: int, checkpoint: str, status: str) -> None:
    """Store a running or paused run's state after a step."""
    with connect() as conn:
        conn.execute("UPDATE runs SET checkpoint = ?, status = ? WHERE id = ?", (checkpoint, status, run_id))


def get_checkpoint(run_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT checkpoint FROM runs WHERE id = ?", (run_id,)).fetchone()
        return row["checkpoint"] if row else None


def reopen_run(run_id: int) -> None:
    """Mark a resumed run as running again."""
    with connect() as conn:
        conn.execute("UPDATE runs SET status = 'running', ended_at = NULL WHERE id = ?", (run_id,))


def resumable_runs(project_id: str | None = None) -> list[dict]:
    """Runs that stopped mid-way (a restart or an error) and kept a checkpoint, newest first."""
    marks = ", ".join("?" * len(RESUMABLE))
    sql = f"SELECT {RUN_FIELDS} FROM runs WHERE checkpoint IS NOT NULL AND status IN ({marks})"
    params: list = list(RESUMABLE)
    if project_id is not None:
        sql += " AND project_id = ?"
        params.append(project_id)
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql + " ORDER BY id DESC", params).fetchall()]


def run_messages(run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT agent_name, content, message_type, model FROM messages WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_runs(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {RUN_FIELDS} FROM runs WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
        return [dict(row) for row in rows]


# ─── Workspace files ─────────────────────────────────────────


def record_file(run_id: int, path: str, before: str | None, after: str) -> None:
    """Note that a run wrote a file. The first before-image a run records is kept."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_files (run_id, path, before_text, after_text) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(run_id, path) DO UPDATE SET after_text = excluded.after_text",
            (run_id, path, before, after),
        )


def run_files(run_id: int) -> list[dict]:
    """The files a run wrote: path, before_text (None if it created the file), after_text."""
    with connect() as conn:
        rows = conn.execute("SELECT path, before_text, after_text FROM run_files WHERE run_id = ? ORDER BY path", (run_id,)).fetchall()
        return [dict(row) for row in rows]


# ─── Messages ────────────────────────────────────────────────


def save_message(project_id: str, run_id: int | None, message: dict) -> None:
    """Append a message to a project's history."""
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages (project_id, run_id, agent_name, content, timestamp, message_type, "
            "model, tokens_in, tokens_out, cost_usd, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                run_id,
                message.get("agent_name", ""),
                message.get("content", ""),
                message.get("timestamp") or ts,
                message.get("message_type", "agent"),
                message.get("model"),
                message.get("tokens_in"),
                message.get("tokens_out"),
                message.get("cost_usd"),
                json.dumps(message["data"]) if message.get("data") is not None else None,
            ),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))


def latest_output(project_id: str) -> list[dict]:
    """The agent messages of the project's latest non-review run that produced any."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT agent_name, content FROM messages WHERE project_id = ? AND message_type = 'agent' "
            "AND run_id = (SELECT MAX(m.run_id) FROM messages m JOIN runs r ON r.id = m.run_id "
            "WHERE m.project_id = ? AND m.message_type = 'agent' AND r.mode != 'review') "
            "ORDER BY id ASC",
            (project_id, project_id),
        ).fetchall()
        return [dict(row) for row in rows]


def spend_since(provider: str, since: str) -> float:
    """USD spent on a provider's models since an ISO timestamp (UTC)."""
    prefix = provider + ":"
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM messages WHERE substr(model, 1, ?) = ? AND timestamp >= ?",
            (len(prefix), prefix, since),
        ).fetchone()
        return float(row[0])


# ─── Benchmarks ──────────────────────────────────────────────


def save_benchmark(model_ref: str, tok_per_sec: float, prefill_tok_per_sec: float | None, hw_fingerprint: str) -> None:
    """Store a model's speed on this machine, replacing any earlier measurement."""
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO benchmarks (model_ref, tok_per_sec, prefill_tok_per_sec, hw_fingerprint, measured_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (model_ref, tok_per_sec, prefill_tok_per_sec, hw_fingerprint, now()),
        )


def get_benchmarks(hw_fingerprint: str) -> dict[str, dict]:
    """This machine's measured speeds, by model ref."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM benchmarks WHERE hw_fingerprint = ?", (hw_fingerprint,)).fetchall()
        return {row["model_ref"]: dict(row) for row in rows}
