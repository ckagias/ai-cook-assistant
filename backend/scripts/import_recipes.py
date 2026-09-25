#!/usr/bin/env python3
"""CLI to import recipes from supported sites (Phase 6).

Usage examples:
  python scripts/import_recipes.py akis_petretzikis --limit 5
  python scripts/import_recipes.py akis_petretzikis --ids 2555,4791
  python scripts/import_recipes.py akis_petretzikis --category kotopulo --limit 20
  python scripts/import_recipes.py akis_petretzikis --all

This script dispatches to the importer module under `app.importers` and
writes staged files using the importer's staging helpers. It never lets
one recipe failure stop the whole run.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from typing import List


SITES = {
    "akis_petretzikis": "app.importers.akis_petretzikis",
}


def confirm(prompt: str) -> bool:
    try:
        ans = input(prompt + " [y/N]: ")
    except Exception:
        return False
    return ans.lower().startswith("y")


def run_site(site: str, ids: List[str], category: str | None, limit: int | None, all_flag: bool, force_refetch: bool) -> int:
    if site not in SITES:
        print(f"Unknown site: {site}")
        return 2

    module_name = SITES[site]
    mod = importlib.import_module(module_name)

    # Discover IDs
    if ids:
        discover_ids = ids
    else:
        opts = getattr(mod, "DiscoveryOptions", None)
        if opts is None:
            # fall back to constructing a simple options object
            class O:
                def __init__(self, category=None, ids=None, limit=None):
                    self.category = category
                    self.ids = ids
                    self.limit = limit

            options = O(category=category, ids=None, limit=limit)
        else:
            options = opts(category=category, ids=None, limit=limit)

        try:
            discover_ids = list(mod.discover(options))
        except Exception as exc:
            print(f"Discovery failed: {exc}")
            return 3

    if not discover_ids:
        print("No recipes discovered.")
        return 0

    if all_flag:
        est = len(discover_ids)
        print(f"About to fetch {est} recipes. This may take a while.")
        if not confirm("Proceed?"):
            print("Aborted.")
            return 0

    successes = 0
    skipped = 0
    failures = []

    for i, rid in enumerate(discover_ids, start=1):
        print(f"[{i}/{len(discover_ids)}] fetching recipe {rid}...")
        try:
            staged = mod.fetch_normalize_and_stage(rid, force_refetch=force_refetch)
            print(f"  fetched and staged: {getattr(staged,'source_id', rid)}")
            successes += 1
        except Exception as exc:
            print(f"  FAILED: {exc}")
            failures.append((rid, str(exc)))

    print()
    print(f"Done: fetched={successes}, failed={len(failures)}")
    if failures:
        print("Failures:")
        for rid, reason in failures:
            print(f"  {rid}: {reason}")
    return 0 if not failures else 4


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Import recipes from supported sites")
    p.add_argument("site", choices=list(SITES.keys()))
    group = p.add_mutually_exclusive_group()
    group.add_argument("--ids", help="Comma-separated source ids to fetch")
    group.add_argument("--category", help="Category slug to filter discovery")
    p.add_argument("--limit", type=int, help="Limit number of discovered recipes")
    p.add_argument("--all", action="store_true", help="Import the whole catalog (prompts for confirmation)")
    p.add_argument("--force-refetch", action="store_true", help="Force re-fetching and overwriting staged files")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    ids = args.ids.split(",") if args.ids else []
    return run_site(args.site, ids=ids, category=args.category, limit=args.limit, all_flag=args.all, force_refetch=args.force_refetch)


if __name__ == "__main__":
    sys.exit(main())
