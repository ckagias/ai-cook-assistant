#!/usr/bin/env python3
"""CLI to import recipes into the local database as *staged* (unreviewed) recipes.

Any recipe site publishing schema.org/Recipe data (most do):
  python scripts/import_recipes.py url --urls https://site/recipe-a,https://site/recipe-b
  python scripts/import_recipes.py url --url-file my_recipes.txt          # one URL per line
  python scripts/import_recipes.py url --sitemap https://site/sitemap.xml --pattern /recipe/ --limit 20
  options: --force-refetch (ignore the 7-day freshness check), --browser-ua (opt-in),
           --yes (skip the confirmation a sitemap run without --limit asks for)

Legacy site-specific importer (writes JSON staging files):
  python scripts/import_recipes.py akis_petretzikis --limit 5
  python scripts/import_recipes.py akis_petretzikis --ids 2555,4791

Then review and publish with scripts/curate_recipe.py. It never lets one recipe's failure
stop the whole run.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import List

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


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


def run_urls(urls: List[str], *, force_refetch: bool, browser_ua: bool) -> int:
    from app.importers import generic

    counts: dict[str, int] = {}
    problems = []
    for i, url in enumerate(urls, start=1):
        result = generic.import_url(url, force=force_refetch, browser_ua=browser_ua)
        counts[result.status] = counts.get(result.status, 0) + 1
        label = f"-> {result.recipe_id}" if result.recipe_id else ""
        print(f"[{i}/{len(urls)}] {result.status.upper():<8} {url} {label}\n{'':>12}{result.message}")
        if result.status in ("failed", "blocked"):
            problems.append(result)

    print("\nDone: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if counts.get("staged"):
        print("Review and publish with: python scripts/curate_recipe.py --list")
    return 4 if any(p.status == "failed" for p in problems) else 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Import recipes into the local database (staged, pending curation)")
    p.add_argument("site", choices=["url", *SITES.keys()])
    group = p.add_mutually_exclusive_group()
    group.add_argument("--ids", help="(akis_petretzikis) comma-separated source ids to fetch")
    group.add_argument("--category", help="(akis_petretzikis) category slug to filter discovery")
    group.add_argument("--urls", help="(url) comma-separated recipe page URLs")
    group.add_argument("--url-file", type=Path, help="(url) text file with one recipe URL per line")
    group.add_argument("--sitemap", help="(url) sitemap or sitemap-index URL to discover recipe pages from")
    p.add_argument("--pattern", help="(url --sitemap) regex a page URL must match, e.g. /recipe/")
    p.add_argument("--limit", type=int, help="Limit number of discovered recipes")
    p.add_argument("--all", action="store_true", help="(akis_petretzikis) import the whole catalog (prompts for confirmation)")
    p.add_argument("--force-refetch", action="store_true", help="Ignore the 7-day freshness check / staged files")
    p.add_argument("--browser-ua", action="store_true", help="(url) send a browser User-Agent instead of an honest one")
    p.add_argument("--yes", action="store_true", help="(url) don't ask before a sitemap run without --limit")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.site == "url":
        if args.urls:
            urls = [u.strip() for u in args.urls.split(",") if u.strip()]
        elif args.url_file:
            urls = [line.strip() for line in args.url_file.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")]
        elif args.sitemap:
            from app.importers import generic

            urls = generic.discover_sitemap(args.sitemap, args.pattern, args.limit)
            print(f"Found {len(urls)} matching URLs in the sitemap.")
            if args.limit is None and len(urls) > 10 and not args.yes:
                if not confirm(f"Import all {len(urls)} (at >= 1 s per page)?"):
                    print("Aborted - pass --limit N to try a few first.")
                    return 0
        else:
            print("url mode needs --urls, --url-file or --sitemap", file=sys.stderr)
            return 2
        if args.limit is not None:
            urls = urls[: args.limit]
        return run_urls(urls, force_refetch=args.force_refetch, browser_ua=args.browser_ua)

    ids = args.ids.split(",") if args.ids else []
    return run_site(args.site, ids=ids, category=args.category, limit=args.limit, all_flag=args.all, force_refetch=args.force_refetch)


if __name__ == "__main__":
    sys.exit(main())
