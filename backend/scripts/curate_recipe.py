#!/usr/bin/env python3
"""Interactive curation CLI for staged external recipes."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.curation.merge import merge_recipe
from app.curation.staged import get_staged
from app.curation.workflow import run_curation


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (2, 4):
        print("Usage: python scripts/curate_recipe.py <source> <source_id> [--out-id <recipe-id>]", file=sys.stderr)
        return 1

    source = args[0]
    source_id = args[1]
    out_id = None
    if len(args) == 4 and args[2] == "--out-id":
        out_id = args[3]

    staged = get_staged(source, source_id)
    if staged is None:
        print(f"No staged recipe found for source={source!r}, source_id={source_id!r}", file=sys.stderr)
        return 1

    try:
        recipe = run_curation(staged)
    except ValueError as exc:
        print(f"Curation aborted: {exc}", file=sys.stderr)
        return 2

    if out_id:
        recipe.id = out_id

    merge_recipe(recipe)
    print(f"\nMerged recipe into {recipe.id} at {BACKEND_DIR / 'data' / 'recipes.json'}")
    print("\nFINAL RECIPE:")
    print(recipe.model_dump_json(indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
