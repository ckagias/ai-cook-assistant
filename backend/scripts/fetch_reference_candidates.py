#!/usr/bin/env python3
"""Fetch candidate reference photos from Wikimedia Commons for eye-checking
before installing one with add_reference.py.

Every run's output must be eye-checked before installing anything - searches
can and do return completely wrong images (e.g. anatomical diagrams for
"boiling water").

Usage: python scripts/fetch_reference_candidates.py [recipe_id]
"""
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BACKEND_DIR / "data" / "reference_candidates"

# Wikimedia's API etiquette policy requires a real, descriptive User-Agent -
# this is someone else's free service.
USER_AGENT = "AICookAssistantReferencePhotoFetcher/1.0 (https://github.com/ckagias/ai-cook-assistant; educational hackathon project)"

API_URL = "https://commons.wikimedia.org/w/api.php"

MAX_CANDIDATES_PER_SLOT = 3
RASTER_EXTENSIONS = (".jpg", ".jpeg", ".png")
# Not every Commons file is free - only accept a licence that actually matches a reusable pattern.
# Wikimedia's actual LicenseShortName strings use a space, not a hyphen, between "CC" and "BY"
# (e.g. "CC BY-SA 4.0"), so the marker below is "cc by", not "cc-by".
FREE_LICENSE_MARKERS = ("cc0", "cc-by", "cc by", "public domain", "pd-", "attribution")

# Targeting the cooking STAGE, not the finished dish.
SLOTS = {
    ("pasta", 0): "pasta boiling water pot",
    ("pasta", 1): "spaghetti cooking in boiling water",
    ("pancakes", 2): "pancake batter cooking on griddle bubbles",
    ("pancakes", 3): "pancake flipping in frying pan",
    ("scrambled_eggs", 1): "scrambled eggs cooking in pan",
}


def api_get(params: dict, max_retries: int = 5) -> dict:
    headers = {"User-Agent": USER_AGENT}
    delay = 1.0
    for attempt in range(max_retries):
        resp = httpx.get(API_URL, params={**params, "format": "json"}, headers=headers, timeout=15.0)
        if resp.status_code == 429:
            print(f"  (rate limited, waiting {delay:.1f}s...)")
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"gave up after {max_retries} retries against {API_URL}")


def search_files(query: str, limit: int = 15) -> list[str]:
    data = api_get(
        {
            "action": "query",
            "list": "search",
            "srnamespace": 6,  # File: namespace - Commons namespace 6 also holds PDFs/scanned books
            "srsearch": query,
            "srlimit": limit,
        }
    )
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def get_image_info(titles: list[str]) -> dict:
    if not titles:
        return {}
    data = api_get(
        {
            "action": "query",
            "titles": "|".join(titles),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
        }
    )
    pages = data.get("query", {}).get("pages", {})
    return {page["title"]: page for page in pages.values() if "imageinfo" in page}


def is_raster(info: dict) -> bool:
    mime = info.get("mime", "")
    url = info.get("url", "")
    return mime.startswith("image/jpeg") or mime.startswith("image/png") or url.lower().endswith(RASTER_EXTENSIONS)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def extract_license(extmetadata: dict) -> tuple[str, str, str]:
    def field(name):
        return extmetadata.get(name, {}).get("value", "")

    return field("LicenseShortName"), strip_html(field("Artist")), strip_html(field("Credit"))


def is_free_license(license_short: str) -> bool:
    lowered = license_short.lower()
    return any(marker in lowered for marker in FREE_LICENSE_MARKERS)


def fetch_slot(recipe_id: str, step_index: int, query: str) -> list[dict]:
    print(f"[{recipe_id}/{step_index}] searching: {query!r}")
    titles = search_files(query)
    if not titles:
        print("  no results")
        return []

    info_by_title = get_image_info(titles)

    slot_dir = STAGING_DIR / f"{recipe_id}_{step_index}"
    candidates = []

    for title in titles:
        if len(candidates) >= MAX_CANDIDATES_PER_SLOT:
            break
        page = info_by_title.get(title)
        if not page:
            continue
        infos = page.get("imageinfo")
        if not infos:
            continue
        info = infos[0]
        if not is_raster(info):
            continue

        license_short, artist, credit = extract_license(info.get("extmetadata", {}))
        if not is_free_license(license_short):
            continue

        url = info["url"]
        # Wikimedia image URLs often carry query-string params (tracking, thumb
        # sizing) - extracting the suffix from the raw URL would bake those
        # into the filename (and any "&" there would break a pasted shell command).
        ext = Path(urlsplit(url).path).suffix or ".jpg"
        slot_dir.mkdir(parents=True, exist_ok=True)
        local_path = slot_dir / f"candidate_{len(candidates) + 1}{ext}"

        print(f"  downloading {title} ({license_short}) -> {local_path.relative_to(BACKEND_DIR)}")
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        local_path.write_bytes(resp.content)

        candidates.append(
            {
                "recipe_id": recipe_id,
                "step_index": step_index,
                "title": title,
                "local_path": str(local_path.relative_to(BACKEND_DIR)),
                "source_url": url,
                "page_url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                "license": license_short,
                "author": artist,
                "credit": credit,
            }
        )

    if not candidates:
        print("  no usable (raster + freely-licensed) candidates found")
    return candidates


def main() -> int:
    requested_recipe = sys.argv[1] if len(sys.argv) > 1 else None

    slots = {k: v for k, v in SLOTS.items() if requested_recipe is None or k[0] == requested_recipe}
    if not slots:
        print(f"ERROR: no slots declared for recipe_id={requested_recipe!r}", file=sys.stderr)
        return 1

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    all_candidates = []
    for (recipe_id, step_index), query in slots.items():
        all_candidates.extend(fetch_slot(recipe_id, step_index, query))
        print()

    manifest_path = STAGING_DIR / "candidates.json"
    manifest_path.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote manifest: {manifest_path.relative_to(BACKEND_DIR)} ({len(all_candidates)} candidates)")

    print()
    print('EYE-CHECK every candidate before installing anything - searches can and do')
    print('return completely wrong images (e.g. anatomical diagrams for "boiling water").')
    print()
    print("To install a chosen candidate:")
    for c in all_candidates:
        print(f"  python scripts/add_reference.py {c['recipe_id']} {c['step_index']} {c['local_path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
