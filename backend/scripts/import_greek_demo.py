#!/usr/bin/env python3
"""One-command import of curated Greek demo recipes into the local database.

This script imports recipes from popular Greek recipe sites (Akis Petretzikis,
Argiro Barbarigou) listed in data/greek_demo_urls.txt into the local database as
staged recipes (pending human safety review).

Usage:
  python scripts/import_greek_demo.py [--limit N] [--force]
  python scripts/curate_recipe.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts import import_recipes  # noqa: E402

URLS_FILE = BACKEND_DIR / "data" / "greek_demo_urls.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import curated Greek demo recipes into local staging database")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of recipes to import")
    parser.add_argument("--force", action="store_true", help="Force refetch even if fetched in last 7 days")
    args = parser.parse_args(argv)

    if not URLS_FILE.exists():
        print(f"Error: {URLS_FILE} not found.", file=sys.stderr)
        return 1

    urls = [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if args.limit:
        urls = urls[: args.limit]

    print(f"Importing {len(urls)} Greek demo recipes from {URLS_FILE.name}...")
    rc = import_recipes.run_urls(urls, force_refetch=args.force, browser_ua=True)
    if rc == 0:
        print("\nNext step:")
        print("Review safety fields with:")
        print("  python scripts/curate_recipe.py --list")
        print("  python scripts/curate_recipe.py <staged-id>")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
