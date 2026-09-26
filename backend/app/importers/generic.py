"""Import a recipe from any web page that publishes it as schema.org/Recipe (JSON-LD,
microdata) - which is most recipe sites, because search engines reward it.

Parsing is done by the MIT-licensed `recipe-scrapers` library (725 site-specific scrapers plus
a generic schema.org fallback); fetching stays in importers/http.py (per-host rate floor,
backoff). Results land in the database as *staged* recipes: nothing imported is served to the
app until a human curates it (scripts/curate_recipe.py).

Being a good citizen: robots.txt is checked before every fetch, the User-Agent says who we are
(the browser one is opt-in), and a URL fetched in the last 7 days isn't fetched again.
Scraped text and photos belong to their authors - source URL and author are stored for
attribution; this is for personal/demo use, and republishing needs the site's permission.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from app import recipes as recipes_module
from app.detection.vocabulary import load_vocabulary
from app.schemas import EquipmentItem, IngredientLine, Recipe, RecipeSource, RecipeStep, RecipeTimes

from . import enrich
from . import http
from .base import DiscoveryOptions

SITE_ID = "web"
HONEST_UA = "CookAssistantImporter/0.1 (personal recipe import; honours robots.txt)"
REFETCH_AFTER = timedelta(days=7)
MAX_SITEMAPS = 20  # a sitemap index can fan out; don't crawl a whole site by accident

_robots_cache: dict[str, Optional[RobotFileParser]] = {}


@dataclass
class ImportResult:
    url: str
    status: str  # "staged" | "skipped" | "blocked" | "failed"
    recipe_id: Optional[str] = None
    message: str = ""


def staged_id_for(url: str) -> str:
    """Staged records get an opaque id derived from the URL - never from page content, so no
    remote text can influence anything id-shaped. The curator picks the real id on publish."""
    return "s-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- politeness


def robots_allows(url: str, user_agent: str, fetch: Callable = None) -> bool:
    """robots.txt verdict for `url`. Missing robots.txt (4xx) = allowed; unreachable or 5xx =
    not allowed, the conservative reading. Cached per host for the process."""
    fetch = fetch or (lambda u: http.get(u, user_agent=user_agent, max_retries=2))
    parts = urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots_cache:
        parser = RobotFileParser()
        try:
            resp = fetch(host + "/robots.txt")
            parser.parse(resp.text.splitlines())
        except RuntimeError as exc:
            if re.search(r"status: 4\d\d", str(exc)):
                parser.parse([])  # no robots.txt at all: everything allowed
            else:
                parser = None
        _robots_cache[host] = parser
    parser = _robots_cache[host]
    return parser is not None and parser.can_fetch(user_agent, url)


# ---------------------------------------------------------------- parsing


def _try(fn, default=None):
    try:
        value = fn()
    except Exception:  # recipe-scrapers raises for every field a page doesn't provide
        return default
    return default if value in (None, "", [], {}) else value


def _schema_tools(scraper) -> list[str]:
    """schema.org `tool` (HowToTool) - the generic scraper doesn't expose it, so read the raw JSON-LD."""
    data = getattr(getattr(scraper, "schema", None), "data", None) or {}
    tools = data.get("tool") or []
    if isinstance(tools, (str, dict)):
        tools = [tools]
    names = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else tool
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def parse_recipe_html(html: str, url: str) -> dict:
    """Everything the page says about the recipe, as plain JSON-able data (also stored raw)."""
    from recipe_scrapers import scrape_html

    scraper = scrape_html(html, org_url=url, supported_only=False)
    title = _try(scraper.title)
    instructions = _try(scraper.instructions_list, [])
    if not title or not instructions:
        raise ValueError("no schema.org Recipe with a title and instructions found on the page")
    language = (_try(scraper.language) or "en").split("-")[0].lower()
    groups = _try(scraper.ingredient_groups, [])
    return {
        "url": _try(scraper.canonical_url) or url,
        "site": urlparse(url).netloc.lower(),
        "title": title,
        "language": language,
        "description": _try(scraper.description),
        "author": _try(scraper.author),
        "yields": _try(scraper.yields),
        "prep_min": _try(scraper.prep_time),
        "cook_min": _try(scraper.cook_time),
        "total_min": _try(scraper.total_time),
        "ingredients": _try(scraper.ingredients, []),
        "ingredient_groups": [{"purpose": g.purpose, "ingredients": list(g.ingredients)} for g in groups],
        "instructions": [s.strip() for s in instructions if s and s.strip()],
        "equipment": _try(scraper.equipment, []) or _schema_tools(scraper),
        "nutrients": _try(scraper.nutrients, {}),
        "image": _try(scraper.image),
        "category": _try(scraper.category),
        "cuisine": _try(scraper.cuisine),
    }


def _as_int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def build_staged_recipe(fields: dict, url: str, fetched_at: str) -> Recipe:
    lang = fields["language"]
    purpose_of = {}
    for group in fields.get("ingredient_groups") or []:
        for line in group["ingredients"]:
            if group.get("purpose"):
                purpose_of.setdefault(line, group["purpose"])
    details = []
    for line in fields["ingredients"]:
        qty, unit, name = enrich.parse_ingredient_line(line)
        details.append(IngredientLine(
            raw_text=line, quantity=qty, unit=unit, name=name, group=purpose_of.get(line),
            vocab_id=enrich.ingredient_vocab_id(line),
        ))

    equipment = [EquipmentItem(name=n, vocab_id=enrich.equipment_vocab_id(n)) for n in fields.get("equipment") or []]
    listed = {e.vocab_id for e in equipment if e.vocab_id}
    vocab = load_vocabulary()
    for vocab_id in enrich.infer_equipment(fields["instructions"]):
        if vocab_id not in listed:
            equipment.append(EquipmentItem(name=vocab.by_id(vocab_id).en, vocab_id=vocab_id, inferred=True))

    steps = [
        RecipeStep(index=i, instruction={lang: text}, suggested_duration_sec=enrich.duration_seconds(text))
        for i, text in enumerate(fields["instructions"])
    ]
    times = RecipeTimes(prep_min=_as_int(fields.get("prep_min")), cook_min=_as_int(fields.get("cook_min")),
                        total_min=_as_int(fields.get("total_min")))
    nutrition = {str(k): str(v) for k, v in (fields.get("nutrients") or {}).items()}
    staged_id = staged_id_for(url)
    return Recipe(
        id=staged_id,
        name={lang: fields["title"]},
        aliases={},
        ingredients=list(fields["ingredients"]),
        steps=steps,
        source=RecipeSource(site=fields["site"], source_id=staged_id, url={lang: url}, imported_at=fetched_at,
                            author=fields.get("author"), fetched_at=fetched_at),
        description={lang: fields["description"]} if fields.get("description") else {},
        language=lang,
        servings=fields.get("yields"),
        times=times if any(v is not None for v in times.model_dump().values()) else None,
        cuisine=fields.get("cuisine"),
        category=fields.get("category"),
        image_url=fields.get("image"),
        nutrition=nutrition,
        ingredient_details=details,
        equipment=equipment,
    )


# ---------------------------------------------------------------- import


def import_url(url: str, *, force: bool = False, browser_ua: bool = False, now: Callable[[], datetime] = _now) -> ImportResult:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ImportResult(url, "failed", message="not an http(s) URL")

    existing = recipes_module.find_source(url)
    if existing:
        if existing["status"] == recipes_module.PUBLISHED:
            # A curated recipe is never overwritten by a re-import.
            return ImportResult(url, "skipped", existing["recipe_id"], "already curated and published")
        fetched = existing.get("fetched_at")
        if not force and fetched and now() - datetime.fromisoformat(fetched.replace("Z", "+00:00")) < REFETCH_AFTER:
            return ImportResult(url, "skipped", existing["recipe_id"], "fetched in the last 7 days (--force-refetch to redo)")

    user_agent = http.USER_AGENT if browser_ua else HONEST_UA
    if not robots_allows(url, user_agent):
        return ImportResult(url, "blocked", message="robots.txt disallows this URL (or robots.txt was unreachable)")
    try:
        resp = http.get(url, user_agent=user_agent, max_retries=3)
        fields = parse_recipe_html(resp.text, url)
        fetched_at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
        recipe = build_staged_recipe(fields, url, fetched_at)
        recipes_module.save_recipe(recipe, status=recipes_module.STAGED, raw_source=fields)
    except Exception as exc:  # one bad page never stops a batch
        return ImportResult(url, "failed", message=f"{type(exc).__name__}: {exc}")
    return ImportResult(url, "staged", recipe.id, f"{fields['title']} ({len(recipe.steps)} steps, {len(recipe.ingredients)} ingredients)")


def discover_sitemap(sitemap_url: str, pattern: Optional[str] = None, limit: Optional[int] = None,
                     user_agent: str = HONEST_UA) -> list[str]:
    """Recipe URLs from a sitemap (or sitemap index), filtered by a regex, capped by `limit`."""
    rx = re.compile(pattern) if pattern else None
    queue, seen_maps, urls = [sitemap_url], 0, []
    while queue and seen_maps < MAX_SITEMAPS and (limit is None or len(urls) < limit):
        current = queue.pop(0)
        seen_maps += 1
        root = ET.fromstring(http.get(current, user_agent=user_agent, max_retries=3).content)
        is_index = root.tag.endswith("sitemapindex")
        for loc in root.iter():
            if not loc.tag.endswith("loc") or not loc.text:
                continue
            value = loc.text.strip()
            if is_index:
                queue.append(value)
            elif rx is None or rx.search(value):
                if value not in urls:
                    urls.append(value)
    return urls[:limit] if limit is not None else urls


class GenericWebSource:
    """RecipeSource protocol adapter (importers/base.py): recipe identifiers are URLs."""

    site_id = SITE_ID

    def discover(self, options: DiscoveryOptions) -> Iterator[str]:
        urls = options.ids or []
        yield from (urls[: options.limit] if options.limit is not None else urls)

    def fetch_and_normalize(self, recipe_id: str) -> dict:
        resp = http.get(recipe_id, user_agent=HONEST_UA, max_retries=3)
        return parse_recipe_html(resp.text, recipe_id)
