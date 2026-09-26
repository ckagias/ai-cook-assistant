#!/usr/bin/env python3
"""Create/migrate the local recipe database and seed it from data/recipes.json.

Usage:
  python scripts/db_init.py            # create + migrate; seeds only if the database is empty
  python scripts/db_init.py --reseed   # re-apply data/recipes.json over the published recipes
                                       # (imported/staged recipes are left alone)
  python scripts/db_init.py --status   # counts only

The app does the first step by itself on startup, so this is mostly for scripting and CI.
Database path: DB_PATH from the environment, default backend/data/cook.db (gitignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import db, recipes  # noqa: E402


def status() -> None:
    with db.session() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM recipes GROUP BY status").fetchall()
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    counts = {r["status"]: r["n"] for r in rows}
    print(f"{db.db_path()}: schema v{version}, {counts.get('published', 0)} published, {counts.get('staged', 0)} staged")


def main(argv: list[str]) -> int:
    recipes.ensure_ready()
    if "--reseed" in argv:
        with db.session() as conn:
            count = recipes.seed_from_json(conn)
        print(f"Re-applied {count} recipes from {recipes.SEED_PATH}")
    status()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
