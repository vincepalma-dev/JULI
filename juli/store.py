"""
SQLite store (WAL): projects, runs, messages.

Each task gets its own run row, so history is never deleted when a new task
starts. Deleting a project cascades to its runs and messages.
"""

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
}


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
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        for column, decl in _MESSAGE_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {column} {decl}")
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


def get_project(project_id: str) -> dict | None:
    """Project metadata with its full message history across all runs."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        project = dict(row)
        msg_rows = conn.execute(
            "SELECT agent_name, content, timestamp, message_type FROM messages "
            "WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        project["messages"] = [dict(mr) for mr in msg_rows]
        return project


def delete_project(project_id: str) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0


# ─── Runs ────────────────────────────────────────────────────


def create_run(project_id: str, prompt: str, mode: str) -> int:
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (project_id, prompt, mode, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (project_id, prompt, mode, ts),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
        return int(cur.lastrowid or 0)


def finish_run(run_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE runs SET status = ?, ended_at = ? WHERE id = ?", (status, now(), run_id))


def get_runs(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM runs WHERE project_id = ? ORDER BY id ASC", (project_id,)).fetchall()
        return [dict(row) for row in rows]


# ─── Messages ────────────────────────────────────────────────


def save_message(project_id: str, run_id: int | None, message: dict) -> None:
    """Append a message to a project's history."""
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages (project_id, run_id, agent_name, content, timestamp, message_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                run_id,
                message.get("agent_name", ""),
                message.get("content", ""),
                message.get("timestamp") or ts,
                message.get("message_type", "agent"),
            ),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
