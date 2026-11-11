"""
What JULI keeps, for how long, and deleting all of it.

Retention: run history (prompts, agent messages, tool and command output,
diffs, checkpoints) is kept for settings["data"]["retention_days"] after a
run ends, or until deleted when that is empty. Old runs are pruned when JULI
starts, after each run, and when the setting is saved. Projects and their
workspace files stay until you delete them; deleting a project keeps its
files on disk. Settings, keys and model benchmarks stay until you change or
remove them.

Delete all: every project, run and benchmark, the workspace files, settings
(back to the defaults) and the keys and tokens JULI saved in the keychain.
Not JULI's to delete: a .env file, models in Ollama, Docker images.
"""

import logging
import os
import shutil
import sqlite3
import stat
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from juli import config, keystore, mcp, providers, store

log = logging.getLogger(__name__)


def apply_retention(settings: dict | None = None) -> int:
    """Delete run history past the retention period. Returns how many runs went."""
    days = ((settings or config.load_settings()).get("data") or {}).get("retention_days")
    if not days:
        return 0
    before = (datetime.now(UTC) - timedelta(days=int(days))).isoformat()
    try:
        deleted = store.prune_runs(before)
    except sqlite3.Error:
        log.exception("Couldn't delete old runs; trying again next time")  # housekeeping: never block a run or startup
        return 0
    if deleted:
        log.info("Deleted %d run(s) older than %d days", deleted, days)
    return deleted


def _writable_then_retry(func: Callable[[str], object], path: str, _exc: object) -> None:
    # git marks its object files read-only, which stops a delete on Windows.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _remove_tree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_writable_then_retry)
    else:
        shutil.rmtree(path, onerror=_writable_then_retry)


def delete_all() -> dict:
    """Delete everything JULI stores. Returns what was done and what couldn't be.
    Doesn't touch the message bus: call it through message_bus.delete_all."""
    problems: list[str] = []
    settings = config.load_settings()

    try:
        store.delete_all()
    except sqlite3.Error as e:
        log.exception("Deleting the database contents failed")
        problems.append(f"The projects and run history couldn't be deleted ({e}). Close other JULI windows and try again.")

    workspaces = config.data_dir() / "workspace"
    if workspaces.exists():
        try:
            _remove_tree(workspaces)
        except OSError as e:
            problems.append(f"Some workspace files couldn't be deleted ({e.strerror or e}). Close the terminal and try again.")

    # The keychain can't list its entries, so remove every name JULI could have used.
    names = {*providers.PROVIDERS, *settings.get("providers", []), *(settings.get("endpoints") or {})}
    names |= {mcp.token_key(name) for name in settings.get("mcp_servers") or {}}
    try:
        for name in sorted(names):
            keystore.delete_key(name)
    except keystore.KeystoreUnavailable:
        problems.append("The system keychain isn't available, so no keys were removed from it.")

    # Defaults, not an empty file: a missing settings.json would import the legacy one again.
    with config.settings_lock:
        config.save_settings(config.default_settings())
    return {"status": "deleted" if not problems else "partly deleted", "problems": problems}
