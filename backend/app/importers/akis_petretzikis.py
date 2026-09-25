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
"""Akis Petretzikis importer.

Discovery (sitemap), page parsing, and staged-schema normalize land in later
phases. This module exists so the site_id is reserved and imports succeed.
"""

site_id = "akis_petretzikis"
