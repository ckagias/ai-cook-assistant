"""Local SQLite database (stdlib sqlite3 - no server, no Docker, one file).

Connections are short-lived (one per operation): SQLite opens in well under a millisecond,
and it sidesteps sharing a connection across FastAPI's worker threads.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cook.db"


def db_path() -> Path:
    return Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH)


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """One transaction: commits on success, rolls back on any exception."""
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    return {row[0] for row in conn.execute("SELECT version FROM schema_version")}


def migrate(path: Optional[Path] = None) -> list[int]:
    """Apply pending migrations/NNN_*.sql in order, each atomically. Returns what was applied."""
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")  # readers don't block the importer's writes
        done = applied_versions(conn)
        applied = []
        for script in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
            version = int(script.name[:3])
            if version in done:
                continue
            sql = script.read_text(encoding="utf-8")
            conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO schema_version (version) VALUES ({version});\nCOMMIT;")
            applied.append(version)
        return applied
    finally:
        conn.close()
