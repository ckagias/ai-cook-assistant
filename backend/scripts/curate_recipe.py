#!/usr/bin/env python3
"""Interactive curation: turn a staged (imported, unreviewed) recipe into a published one.

Usage:
  python scripts/curate_recipe.py --list                 # staged recipes waiting in the database
  python scripts/curate_recipe.py <staged-id>            # curate one and publish it
  python scripts/curate_recipe.py <source> <source_id>   # legacy: a JSON-staged Akis Petretzikis recipe
  python scripts/curate_recipe.py --export               # write all published recipes to data/recipes.json

Publishing happens only after the curator confirms every safety-relevant field (which steps
are checkable, which contain raw protein) - nothing imported is ever served before that.
A running backend reads the database on every request, so a published recipe shows up in
GET /recipes immediately.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import recipes as recipes_module  # noqa: E402
from app.curation.merge import export_published_json, merge_recipe  # noqa: E402
from app.curation.staged import get_staged, list_staged_records, staged_from_record  # noqa: E402
from app.curation.workflow import run_curation  # noqa: E402


def list_staged() -> int:
    records = list_staged_records()
    if not records:
        print("No staged recipes. Import some with: python scripts/import_recipes.py url --urls <url>")
        return 0
    print(f"{'staged id':<18} {'lang':<5} {'steps':<6} title / source")
    for r in records:
        title = r.name.get(r.language or "en") or next(iter(r.name.values()), "")
        url = next(iter(r.source.url.values()), "") if r.source else ""
        print(f"{r.id:<18} {r.language or '-':<5} {len(r.steps):<6} {title}\n{'':<31}{url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--list"]:
        return list_staged()
    if args == ["--export"]:
        count = export_published_json()
        print(f"Wrote {count} published recipes to {recipes_module.SEED_PATH}")
        return 0

    replaces = None
    base = None
    if len(args) == 1:
        base = recipes_module.get_recipe(args[0], status=recipes_module.STAGED)
        if base is None:
            print(f"No staged recipe with id {args[0]!r} - see --list", file=sys.stderr)
            return 1
        staged, replaces = staged_from_record(base), base.id
    elif len(args) == 2:
        staged = get_staged(args[0], args[1])
        if staged is None:
            print(f"No staged recipe found for source={args[0]!r}, source_id={args[1]!r}", file=sys.stderr)
            return 1
    else:
        print(__doc__, file=sys.stderr)
        return 1

    try:
        recipe = run_curation(staged, replaces=replaces, base=base)
    except ValueError as exc:
        print(f"Curation aborted: {exc}", file=sys.stderr)
        return 2

    merge_recipe(recipe, replaces=replaces)
    print(f"\nPublished '{recipe.id}' to {recipes_module.db.db_path()}")
    print("Run with --export to also write it into data/recipes.json (the version-controlled seed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
