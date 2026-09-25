"""Discovery of recipe IDs from akispetretzikis.com sitemap (Phase 3).

This module implements the `discover()` half of the importer: fetch the
sitemap.xml, extract recipe URLs of the default locale form
`https://akispetretzikis.com/recipe/<id>/<slug>`, dedupe by id, and yield
ids. Supports `DiscoveryOptions.ids` (validated against the sitemap),
`DiscoveryOptions.category` (simple slug substring match), and
`DiscoveryOptions.limit`.
"""
from __future__ import annotations

import re
from typing import Iterator
import xml.etree.ElementTree as ET

from .base import DiscoveryOptions
from . import http
from . import html_utils
import json
from datetime import datetime, timezone
from pathlib import Path

STAGING_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "imported_recipes_staging" / "akis_petretzikis"
STAGING_ROOT.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = STAGING_ROOT / "manifest.json"

SITEMAP_URL = "https://akispetretzikis.com/sitemap.xml"
RECIPE_URL_RE = re.compile(r"^https://akispetretzikis\.com/recipe/(\d+)/([a-z0-9-]+)$")


def _parse_sitemap(xml_text: str) -> list[tuple[str, str]]:
    """Return list of (id, slug) tuples in document order for default-locale recipe URLs."""
    root = ET.fromstring(xml_text)
    ns = {k: v for k, v in root.attrib.items()}
    ids = []
    # <urlset> contains repeated <url><loc>...</loc></url>
    for url in root.findall(".//{*}url"):
        loc = url.find("{*}loc")
        if loc is None or not loc.text:
            continue
        m = RECIPE_URL_RE.match(loc.text.strip())
        if m:
            ids.append((m.group(1), m.group(2)))
    return ids


def discover(options: DiscoveryOptions) -> Iterator[str]:
    """Yield recipe ids (strings) discovered from the sitemap.

    options.ids: if provided, yield exactly those ids (validated against
    what's present in the sitemap; missing ids raise ValueError).

    options.category: simple filter on the slug (substring match). This is
    intentionally conservative: a future improvement could fetch each
    candidate's page and inspect its `category` field, but for Phase 3 a
    slug-based filter is fast and simple.

    options.limit: cap the number yielded.
    """
    resp = http.get(SITEMAP_URL)
    text = resp.text
    parsed = _parse_sitemap(text)

    # Preserve order while deduping by id
    seen = {}
    for sid, slug in parsed:
        if sid not in seen:
            seen[sid] = slug

    all_ids = list(seen.items())  # list of (id, slug)

    # If a category filter is given, keep only ids whose slug contains the category string
    if options.category:
        cat = options.category.lower()
        all_ids = [(i, s) for (i, s) in all_ids if cat in s]

    sitemap_id_set = {i for (i, _) in list(seen.items())}

    # If options.ids is supplied, validate and yield those in the provided order
    if options.ids:
        missing = [i for i in options.ids if i not in sitemap_id_set]
        if missing:
            raise ValueError(f"requested ids not present in sitemap: {missing}")
        results = [(i, seen[i]) for i in options.ids]
    else:
        results = all_ids

    # Apply limit
    if options.limit is not None and options.limit >= 0:
        results = results[: options.limit]

    for i, _ in results:
        yield i


def _recipe_urls_for_id(recipe_id: str) -> tuple[str, str]:
    # Use a placeholder slug for the default-locale URL; Next.js resolves by id.
    return (
        f"https://akispetretzikis.com/recipe/{recipe_id}/x",
        f"https://akispetretzikis.com/en/recipe/{recipe_id}/x",
    )


def fetch_and_normalize(recipe_id: str) -> dict:
    """Fetch the Greek and English recipe pages, extract their __NEXT_DATA__ JSON,
    and return a dict containing the two raw payloads with HTML stripped where
    appropriate. This function performs only parsing/cleanup; Phase 5 will
    implement the richer normalization into `StagedRecipe`.
    """
    url_el, url_en = _recipe_urls_for_id(recipe_id)
    resp_el = http.get(url_el)
    resp_en = http.get(url_en)

    raw_el = html_utils.extract_next_data(resp_el.text, src_url=url_el)
    raw_en = html_utils.extract_next_data(resp_en.text, src_url=url_en)

    # Helper to walk known free-text fields and strip HTML. We only do a
    # conservative set here that Phase 5 expects: title, method steps,
    # ingredient titles and ingredient info. If the structure differs, leave
    # the raw payload untouched so Phase 5 can decide.
    def _strip_fields(raw):
        try:
            # path: props.pageProps.ssRecipe.data
            data = raw.get("props", {}).get("pageProps", {}).get("ssRecipe", {}).get("data", {})
        except Exception:
            return raw

        # Title
        if isinstance(data.get("title"), dict):
            for k, v in data["title"].items():
                data["title"][k] = html_utils.strip_html(v)

        # Method sections: list of {section, steps: [{id, step}]}
        method = data.get("method")
        if isinstance(method, list):
            for sec in method:
                steps = sec.get("steps") or []
                for s in steps:
                    if "step" in s:
                        s["step"] = html_utils.strip_html(s.get("step"))

        # Ingredient sections
        ing_secs = data.get("ingredient_sections")
        if isinstance(ing_secs, list):
            for sec in ing_secs:
                ings = sec.get("ingredients") or []
                for ing in ings:
                    if "title" in ing:
                        ing["title"] = html_utils.strip_html(ing.get("title"))
                    if "info" in ing:
                        ing["info"] = html_utils.strip_html(ing.get("info"))

        return raw

    parsed_el = _strip_fields(raw_el)
    parsed_en = _strip_fields(raw_en)

    return {"source_id": str(recipe_id), "raw_el": parsed_el, "raw_en": parsed_en, "fetched_at": datetime.now(timezone.utc).isoformat()}
"""Akis Petretzikis importer.

Discovery (sitemap), page parsing, and staged-schema normalize land in later
phases. This module exists so the site_id is reserved and imports succeed.
"""

site_id = "akis_petretzikis"
