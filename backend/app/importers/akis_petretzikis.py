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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .schema import StagedRecipe, StagedIngredient, StagedStep, StagedMetadata

STAGING_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "imported_recipes_staging" / "akis_petretzikis"
STAGING_ROOT.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = STAGING_ROOT / "manifest.json"
REFETCH_THRESHOLD = timedelta(days=7)

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

    raw_pair = {"source_id": str(recipe_id), "raw_el": parsed_el, "raw_en": parsed_en, "fetched_at": datetime.now(timezone.utc).isoformat()}
    return raw_pair


def _map_dietary_flags(raw_data: dict) -> dict:
    # Map site-specific flags like is_ve, is_vg, is_gf, is_df, is_ef, is_nf
    mapping = {
        "is_ve": "vegetarian",
        "is_vg": "vegan",
        "is_gf": "gluten_free",
        "is_df": "dairy_free",
        "is_ef": "egg_free",
        "is_nf": "nut_free",
    }
    out = {}
    for raw_key, out_key in mapping.items():
        val = raw_data.get(raw_key)
        if isinstance(val, int):
            out[out_key] = bool(val)
        elif isinstance(val, bool):
            out[out_key] = val
    return out


def normalize(raw_el: dict, raw_en: dict) -> StagedRecipe:
    """Normalize the two parsed __NEXT_DATA__ payloads into a StagedRecipe.

    This is intentionally conservative: it flattens method sections into a
    single steps list, maps ingredient title/info, and extracts metadata.
    """
    # Navigate to the page data
    data_el = raw_el.get("props", {}).get("pageProps", {}).get("ssRecipe", {}).get("data", {})
    data_en = raw_en.get("props", {}).get("pageProps", {}).get("ssRecipe", {}).get("data", {})

    source_id = str(raw_el.get("source_id") or data_el.get("id") or raw_en.get("source_id") or data_en.get("id"))

    title = {"el": (data_el.get("title") or {}).get("el") if isinstance(data_el.get("title"), dict) else (data_el.get("title") or {}),
             "en": (data_en.get("title") or {}).get("en") if isinstance(data_en.get("title"), dict) else (data_en.get("title") or {})}

    # Category: try to copy id/slug if present
    category = {}
    cat = data_el.get("category") or {}
    if isinstance(cat, dict):
        for k in ("id", "slug"):
            if k in cat:
                category[k] = str(cat[k])

    # Ingredients: flatten ingredient_sections
    ingredients = []
    for sec in data_el.get("ingredient_sections") or []:
        for ing in sec.get("ingredients") or []:
            title_el = ing.get("title") if isinstance(ing.get("title"), str) else ing.get("title")
            # build bilingual title where possible
            title_dict = {"el": title_el, "en": None}
            # Quantity/unit/info best-effort
            quantity = str(ing.get("quantity") or "")
            unit = {"el": str(ing.get("unit") or ""), "en": ""}
            info = {"el": str(ing.get("info") or ""), "en": ""}
            ingredients.append(StagedIngredient(title=title_dict, quantity=quantity, unit=unit, info=info))

    # Steps: flatten method sections in order, pair by position where possible
    steps = []
    def _collect_steps(data):
        out = []
        for sec in data.get("method") or []:
            section_title = sec.get("section") or ""
            section_dict = {"el": section_title, "en": section_title}
            for s in sec.get("steps") or []:
                text = s.get("step") or ""
                out.append((section_dict, text))
        return out

    steps_el = _collect_steps(data_el)
    steps_en = _collect_steps(data_en)

    # Zip by position: if counts differ, pad with empty strings
    max_n = max(len(steps_el), len(steps_en))
    for i in range(max_n):
        sec_el, text_el = steps_el[i] if i < len(steps_el) else ({"el": "", "en": ""}, "")
        sec_en, text_en = steps_en[i] if i < len(steps_en) else ({"el": "", "en": ""}, "")
        # prefer localized section title when present
        section = {"el": sec_el.get("el") or sec_en.get("el") or "", "en": sec_en.get("en") or sec_el.get("en") or ""}
        text = {"el": text_el or "", "en": text_en or ""}
        steps.append(StagedStep(section=section, text=text))

    # Metadata
    meta = StagedMetadata()
    try:
        meta.make_time_min = int(data_el.get("make_time")) if data_el.get("make_time") is not None else None
    except Exception:
        meta.make_time_min = None
    try:
        meta.bake_time_min = int(data_el.get("bake_time")) if data_el.get("bake_time") is not None else None
    except Exception:
        meta.bake_time_min = None
    meta.servings = data_el.get("shares")
    meta.difficulty = data_el.get("difficulty")
    meta.equipment = [e.get("title") if isinstance(e, dict) else e for e in data_el.get("equipment_used") or []]
    meta.image_url = None
    if data_el.get("assets") and isinstance(data_el.get("assets"), list) and data_el.get("assets")[0].get("url"):
        meta.image_url = data_el.get("assets")[0].get("url")
    meta.video_url = data_el.get("video_url")
    # Dietary flags mapping
    meta.dietary_flags = _map_dietary_flags(data_el)

    staged = StagedRecipe(
        source="akis_petretzikis",
        source_id=source_id,
        source_url={"el": _recipe_urls_for_id(source_id)[0], "en": _recipe_urls_for_id(source_id)[1]},
        fetched_at=raw_el.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
        title={"el": (data_el.get("title") or "") if isinstance(data_el.get("title"), str) else (data_el.get("title") or {}),
               "en": (data_en.get("title") or "") if isinstance(data_en.get("title"), str) else (data_en.get("title") or {})},
        category=category,
        ingredients=ingredients,
        steps=steps,
        metadata=meta,
    )

    return staged


def write_staged(staged: StagedRecipe, force_refetch: bool = False) -> None:
    """Write a staged recipe JSON and update manifest, idempotent unless forced."""
    out_path = STAGING_ROOT / f"{staged.source_id}.json"

    if out_path.exists() and not force_refetch:
        mtime = datetime.fromtimestamp(out_path.stat().st_mtime, timezone.utc)
        if datetime.now(timezone.utc) - mtime < REFETCH_THRESHOLD:
            # skip write
            return

    try:
        # pydantic v2: model_dump_json exists; fall back to json.dumps(model_dump())
        text = staged.model_dump_json(ensure_ascii=False, indent=2)
    except Exception:
        text = json.dumps(staged.model_dump(), ensure_ascii=False, indent=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    # Update manifest
    manifest = []
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            manifest = []

    # Replace or append entry
    entry = {"source_id": staged.source_id, "title": staged.title, "fetched_at": staged.fetched_at}
    manifest = [m for m in manifest if m.get("source_id") != staged.source_id]
    manifest.append(entry)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_normalize_and_stage(recipe_id: str, force_refetch: bool = False) -> StagedRecipe:
    raw = fetch_and_normalize(recipe_id)
    staged = normalize(raw["raw_el"], raw["raw_en"])
    write_staged(staged, force_refetch=force_refetch)
    return staged
site_id = "akis_petretzikis"
