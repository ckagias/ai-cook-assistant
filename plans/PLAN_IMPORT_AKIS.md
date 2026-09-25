# Import plan: recipes from Akis Petretzikis, phase by phase

**Branch:** `feature/import-akis`
**Owner:** Developer A
**Depends on:** nothing else in this repo. Runs standalone.
**Feeds into:** `PLAN_COMBINE_RECIPES.md` (Developer B), via the staged JSON
contract defined in Phase 5. You do not need Plan 2's code to finish this
plan, and Plan 2's developer does not need your code - only the JSON shape
you both agree to below.

This is a developer/admin CLI tool, matching the existing pattern in this
repo (`scripts/fetch_reference_candidates.py`, `scripts/add_reference.py`):
a person runs it, reviews the output, and nothing it produces is live in the
app until a human curates it (that curation happens in Plan 2). No
end-user-facing import UI in this MVP.

Each phase below is self-contained: what to build and why, a ready-to-paste
prompt, and a suggested commit message. Feed one phase's prompt at a time to
the LLM, review the diff, commit yourself (the LLM should never run `git
commit`), then move to the next phase.

---

## Ground truth about the target site (verified, re-verify before relying on it)

Sites change. Everything below was confirmed by fetching the real site
during planning - Phase 1 asks you to re-confirm it before building on it,
but you don't have to rediscover it from scratch.

- **robots.txt** (`https://akispetretzikis.com/robots.txt`) explicitly
  allows crawling for any user-agent (`User-agent: *` / `Allow: /`). Only
  `googlebot`/`Google-InspectionTool` have narrower rules disallowing
  `/assets/*` and `/icons/*`, which don't matter here.
- **Cloudflare bot protection is present.** A request with a generic/bare
  `User-Agent` (or a non-browser-shaped request) gets **HTTP 403**. A
  request with a realistic desktop-browser `User-Agent` string succeeds.
  Treat occasional 403s as a transient, retryable condition, not a hard
  failure - the same politeness/backoff philosophy as
  `fetch_reference_candidates.py`'s handling of Wikimedia's 429s, because
  this is someone else's site and being a bad citizen risks getting the
  whole project IP-banned.
- **The site is a Next.js app rendered server-side.** Every page (category
  listing, recipe detail) embeds its own data as clean JSON in
  `<script id="__NEXT_DATA__" type="application/json">`. You do **not** need
  a CSS-selector/HTML-scraping approach - extract that one script tag and
  `json.loads()` it.
- **Recipe URLs**: `https://akispetretzikis.com/recipe/<id>/<slug>` (Greek,
  default locale) and `https://akispetretzikis.com/en/recipe/<id>/<slug>`
  (English) - **the same numeric `<id>` serves both language variants**, and
  both are genuinely native text (not machine-translated), confirmed by
  fetching both for the same recipe. This means the importer needs no
  translation step: fetch both URLs for a given id, done.
- **Sitemap**: `https://akispetretzikis.com/sitemap.xml` is a single flat
  `<urlset>` (not a sitemap index) mixing blog posts, category pages, and
  recipes. At verification time it had 14,212 `<loc>` entries, of which
  5,374 matched `https://akispetretzikis.com/recipe/<digits>/<slug>` - this
  is the cheapest way to discover the full recipe catalog without crawling
  category pages.
- **A recipe's `__NEXT_DATA__` JSON** (path:
  `props.pageProps.ssRecipe.data`) contains, among other fields: `id`,
  `slug`, `title`, `video_url`, `method` (list of `{section, steps: [{id,
  step}]}` - step text contains inline HTML entities/tags like `&eacute;`,
  `&deg;`, `<strong>`), `ingredient_sections` (list of `{title,
  ingredients: [{title, unit, quantity, info, conversions}]}`),
  `make_time`/`bake_time` (minutes), `shares` (serving count as a string
  range, e.g. `"4-6"`), `difficulty`, `nutrition` (detailed breakdown),
  dietary flags (`is_ve`, `is_vg`, `is_gf`, `is_df`, `is_ef`, `is_sf`,
  `is_nf`, `is_ls`), `equipment_used`, `assets` (images), `category`.
- A third-party Apify scraper and a third-party Parse.bot API both claim to
  cover this site. **Don't build on either without independently verifying
  they're reliable, current, and legitimate to depend on** - this plan
  assumes you fetch the site directly, since that's verified and under your
  control.

---

## Phase 1 — Package scaffold, generic importer interface, and site notes

**Files:** `backend/app/importers/__init__.py`, `backend/app/importers/base.py`,
`backend/app/importers/akis_petretzikis.py` (empty/stub for now),
`backend/app/importers/SITE_NOTES_akis.md`.

**What this proves:** the shape other sites will plug into later exists
before you write a single line of Akis-specific scraping code, so "later on
we will add many more sites" doesn't mean rewriting this from scratch.

**base.py** - a minimal interface every future site-importer implements.
Keep it small; don't speculatively add methods no current site needs:

```python
from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass
class DiscoveryOptions:
    category: str | None = None
    ids: list[str] | None = None
    limit: int | None = None


class RecipeSource(Protocol):
    site_id: str  # e.g. "akis_petretzikis" - matches the staged JSON's "source" field

    def discover(self, options: DiscoveryOptions) -> Iterator[str]:
        """Yield source-specific recipe identifiers (not full URLs) to fetch."""

    def fetch_and_normalize(self, recipe_id: str) -> dict:
        """Fetch one recipe and return it in the staged schema (Phase 5)."""
```

**SITE_NOTES_akis.md**: re-verify every bullet in "Ground truth about the
target site" above against the live site (things change), and write down
what you found, including anything that's now different. This is the
living reference for Phase 2 onward, and for whoever builds the next site's
importer and wants to see what a filled-in version of this doc looks like.

**Prompt:**
> Scaffold `backend/app/importers/__init__.py`, `backend/app/importers/base.py`
> with the `DiscoveryOptions` dataclass and `RecipeSource` protocol exactly
> as specified (discover() yields recipe identifiers, fetch_and_normalize()
> returns the staged schema dict from Phase 5 of PLAN_IMPORT_AKIS.md - stub
> that phase's shape as a comment for now, it'll be filled in later), and an
> empty `backend/app/importers/akis_petretzikis.py` module. Then fetch
> `https://akispetretzikis.com/robots.txt` and a sample recipe URL yourself
> (e.g. `https://akispetretzikis.com/recipe/2555/kotopoylo-lemonato-me-patates`
> and its `/en/` counterpart) to re-verify the "Ground truth" section of
> PLAN_IMPORT_AKIS.md is still accurate, and write
> `backend/app/importers/SITE_NOTES_akis.md` documenting what you found,
> flagging anything that's changed. Do not commit - stop for review.

**Suggested commit message:** `chore: scaffold generic recipe-importer interface`

---

## Phase 2 — Polite HTTP fetch layer

**Files:** `backend/app/importers/http.py`.

Everything this module does talks to someone else's server. Be a good
citizen the same way `fetch_reference_candidates.py` already is for
Wikimedia:

```python
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# A real desktop-browser UA string, not a bare "MyImporter/1.0" - Cloudflare
# 403s the latter. This is documented, not disguised: SITE_NOTES_akis.md
# records why, and every request is otherwise honest (real timeouts, real
# rate limiting, no attempt to evade robots.txt - which already allows us).

MIN_DELAY_SEC = 1.0  # floor between requests to the same host, regardless of backoff state

def get(url: str, *, max_retries: int = 5) -> httpx.Response:
    # Real timeout (e.g. 15s). Retry with exponential backoff on 403, 429,
    # and 5xx (403 here usually means a transient Cloudflare challenge, not
    # a permanent block - confirmed during planning that a plain retry with
    # the same headers succeeds). Raise on anything else or after max_retries.
    # Enforce MIN_DELAY_SEC between calls even on the happy path - discovering
    # 5000+ recipe URLs is not licence to hit the site as fast as possible.
```

**Prompt:**
> Implement `backend/app/importers/http.py` exactly as described above: a
> real desktop browser User-Agent (document why in a comment, referencing
> SITE_NOTES_akis.md), retry-with-backoff on 403/429/5xx, a hard floor on
> request rate regardless of retry state, and a real per-request timeout.
> Write a small test that mocks the transport (no real network in the test
> suite) covering: a 403 followed by a 200 succeeds after retry, a
> non-retryable status (e.g. 404) raises immediately, and the rate floor is
> actually enforced (two calls issued back-to-back take at least
> MIN_DELAY_SEC). Do not commit - stop for review.

**Suggested commit message:** `feat: polite HTTP fetch layer for recipe importers`

---

## Phase 3 — Recipe discovery via sitemap.xml

**Files:** `backend/app/importers/akis_petretzikis.py` (discovery half).

```python
SITEMAP_URL = "https://akispetretzikis.com/sitemap.xml"
RECIPE_URL_RE = re.compile(r"^https://akispetretzikis\.com/recipe/(\d+)/([a-z0-9-]+)$")

def discover(options: DiscoveryOptions) -> Iterator[str]:
    # Fetch SITEMAP_URL once via http.get(). Parse as XML (stdlib
    # xml.etree.ElementTree - no need for a new dependency), extract every
    # <loc>, filter to RECIPE_URL_RE matches on the DEFAULT-LOCALE (no /en/
    # prefix) form specifically, since that's the canonical id source.
    # Dedupe by id (a sitemap can list the same id more than once via
    # legacy redirects).
    #
    # options.ids: if given, yield exactly those ids (still validated
    #   against the sitemap's set, so a typo'd id fails loudly, not silently).
    # options.category: if given, filter to recipes whose sitemap slug
    #   pattern or a follow-up category lookup (see note below) matches.
    # options.limit: cap the number yielded, applied last - useful for a
    #   test run before committing to importing thousands of recipes.
    #
    # Category filtering needs the numeric category id, not just a slug
    # match on the URL (the recipe URL itself carries no category info) -
    # either fetch each candidate's __NEXT_DATA__ and check its `category`
    # field (simple but slower), or resolve the category slug to an id via
    # a category listing page first and cross-reference (faster, more
    # code). Start simple; a few thousand recipes is not a lot of pages to
    # inspect once if category filtering turns out rare in practice.
```

**Why the sitemap and not crawling category pages:** one request instead of
walking every category listing page and paginating through it, and it's the
same signal search engines use, so it's unlikely to disappear without
notice.

**Prompt:**
> Implement the discovery half of `backend/app/importers/akis_petretzikis.py`
> as described above: fetch and parse the sitemap via the http.py module
> from Phase 2, filter to recipe URLs, dedupe by id, and support
> `DiscoveryOptions.ids`/`.category`/`.limit` from base.py's Phase 1
> interface. Write tests against a small embedded fixture sitemap XML
> string (not the live site) covering: recipe URLs are correctly extracted
> and non-recipe URLs (blog posts, category pages) are excluded, duplicate
> ids are deduped, `ids` filters to exactly those (and errors clearly on an
> id absent from the sitemap), and `limit` caps the result. Do not commit -
> stop for review.

**Suggested commit message:** `feat: discover Akis Petretzikis recipe URLs via sitemap`

---

## Phase 4 — Recipe page parsing

**Files:** `backend/app/importers/akis_petretzikis.py` (parsing half),
`backend/app/importers/html_utils.py`.

```python
def extract_next_data(html: str) -> dict:
    # Find <script id="__NEXT_DATA__" type="application/json">...</script>,
    # json.loads() its contents. Raise a clear, specific error (naming the
    # URL) if the tag is missing - a missing tag means the page structure
    # changed and every recipe fetch from here on is suspect, so this
    # should stop the run, not silently skip one recipe.

def strip_html(text: str | None) -> str:
    # Same job as fetch_reference_candidates.py's strip_html: decode HTML
    # entities (&eacute; -> é, &deg; -> °, &nbsp; -> space) and strip tags
    # (<strong>...</strong>). Source step/ingredient text carries both.
```

`fetch_and_normalize(recipe_id)`:
1. Build both URLs: `https://akispetretzikis.com/recipe/{id}/{slug}` and
   the `/en/` variant. The slug itself is only needed for a human-readable
   URL - Next.js resolves the page by id regardless of slug correctness, so
   if you only have the id (e.g. from `options.ids`), fetch
   `https://akispetretzikis.com/recipe/{id}/x` and read the *real* slug
   back out of the returned `__NEXT_DATA__` rather than guessing it.
2. Fetch both via `http.get()`, extract `__NEXT_DATA__` from each,
   `strip_html()` every free-text field.
3. Hand both parsed objects to Phase 5's normalizer.

**Prompt:**
> Implement `backend/app/importers/html_utils.py` (extract_next_data,
> strip_html) and the parsing half of
> `backend/app/importers/akis_petretzikis.py` as described above. Write
> tests using small embedded HTML fixture strings (not the live site) for
> both extract_next_data (successful extraction, and a clear error when the
> script tag is absent) and strip_html (entity decoding, tag stripping, and
> that a plain string with neither passes through unchanged). Do not commit
> - stop for review.

**Suggested commit message:** `feat: parse Akis Petretzikis recipe pages via embedded Next.js data`

---

## Phase 5 — Normalize into the staged schema (the shared contract with Plan 2)

**Files:** `backend/app/importers/schema.py`.

This is the interface between this plan and `PLAN_COMBINE_RECIPES.md`.
Get this right and both developers can work without ever touching each
other's code. It is deliberately **richer** than the app's own
`Recipe`/`RecipeStep` schema (`backend/app/schemas.py`) - that schema
assumes a human has already made curation decisions (which step is
checkable, which contains raw protein, what to say when checking on it).
This schema captures what the *site* actually said, unedited, so Plan 2's
human curator has the full source material to make those decisions from.

```python
# backend/app/importers/schema.py
from pydantic import BaseModel


class StagedIngredient(BaseModel):
    title: dict[str, str]          # {"el": ..., "en": ...}
    quantity: str = ""
    unit: dict[str, str] = {}      # {} if the site gave no unit
    info: dict[str, str] = {}      # e.g. "medium sized" - {} if none


class StagedStep(BaseModel):
    section: dict[str, str]        # the site's own loose grouping, e.g. "For the chicken"
    text: dict[str, str]           # {"el": ..., "en": ...}, HTML-stripped


class StagedMetadata(BaseModel):
    make_time_min: int | None = None
    bake_time_min: int | None = None
    servings: str | None = None    # site gives a range as a string, e.g. "4-6" - don't force it to an int
    difficulty: str | None = None
    dietary_flags: dict[str, bool] = {}   # vegetarian, vegan, gluten_free, dairy_free, egg_free, nut_free
    equipment: list[str] = []
    image_url: str | None = None
    video_url: str | None = None


class StagedRecipe(BaseModel):
    source: str                    # "akis_petretzikis" - matches RecipeSource.site_id
    source_id: str                 # the site's numeric id, as a string
    source_url: dict[str, str]     # {"el": full URL, "en": full URL}
    fetched_at: str                # ISO 8601 UTC timestamp
    title: dict[str, str]          # {"el": ..., "en": ...}
    category: dict[str, str] = {}  # {"id": "...", "slug": "...", "title_el": "...", "title_en": "..."}
    ingredients: list[StagedIngredient]
    steps: list[StagedStep]        # FLAT list, in source order, across all sections - not grouped yet
    metadata: StagedMetadata
```

`normalize(raw_el: dict, raw_en: dict) -> StagedRecipe`: takes the two
parsed `__NEXT_DATA__` payloads (Greek and English, same id), zips their
`method`/`ingredient_sections` by position (they're the same recipe in the
same structural order in both locales - verify this assumption against a
handful of real recipes and note in SITE_NOTES_akis.md if it ever doesn't
hold), and builds one bilingual `StagedRecipe`. Map `is_ve`/`is_vg`/`is_gf`/
`is_df`/`is_ef`/`is_nf` into `dietary_flags` with clear English keys
(`vegetarian`, `vegan`, `gluten_free`, `dairy_free`, `egg_free`, `nut_free`).

**Write path**: `fetch_and_normalize()` (finishing Phase 1's interface)
writes the result to
`backend/data/imported_recipes_staging/akis_petretzikis/{source_id}.json`
(`ensure_ascii=False`, so Greek text stays readable) and also updates
`backend/data/imported_recipes_staging/akis_petretzikis/manifest.json` - a
flat list of `{source_id, title, fetched_at}` for every staged recipe, so
Plan 2 (or a human) can see what's available without opening every file.
**Idempotent**: if `{source_id}.json` already exists and is younger than
some re-fetch threshold (e.g. 7 days - make it a CLI flag,
`--force-refetch` to ignore it), skip re-fetching that id. This is what
makes a full-catalog run safely resumable after an interruption instead of
starting over.

Add `backend/data/imported_recipes_staging/` to `.gitignore` - matches the
existing `reference_candidates/` entry's reasoning (regenerable staging
output, not source of truth).

**Prompt:**
> Implement `backend/app/importers/schema.py` exactly as specified above,
> and the `normalize()` function plus the staged-write path (idempotent,
> manifest-updating) inside `backend/app/importers/akis_petretzikis.py`,
> completing the `RecipeSource` interface from Phase 1. Add
> `backend/data/imported_recipes_staging/` to `.gitignore`. Write tests
> using two small embedded fixture `__NEXT_DATA__`-shaped dicts (Greek and
> English) covering: normalize() produces the expected StagedRecipe shape,
> dietary flags map to the documented English keys, a second
> fetch_and_normalize() call for the same id within the re-fetch threshold
> does not re-fetch (mock the HTTP layer and assert it wasn't called), and
> the manifest is updated correctly. Do not commit - stop for review.

**Suggested commit message:** `feat: normalize Akis Petretzikis recipes into the staged import schema`

---

## Phase 6 — CLI entry point and end-to-end test

**Files:** `backend/scripts/import_recipes.py`.

```
Usage:
  python scripts/import_recipes.py akis_petretzikis --limit 5
  python scripts/import_recipes.py akis_petretzikis --ids 2555,4791
  python scripts/import_recipes.py akis_petretzikis --category kotopulo --limit 20
  python scripts/import_recipes.py akis_petretzikis --all        # the whole catalog - prints an estimated
                                                                    time based on MIN_DELAY_SEC and warns
                                                                    before starting, requires confirmation
```

Dispatches by site name to a registry (`{"akis_petretzikis": ...}` for now,
one line to add the next site later). Prints progress (`[12/20] fetched
recipe 4791: "Aromatic roast chicken"`), a final summary (fetched / skipped
as already-staged / failed with reasons), and never lets one recipe's
failure stop the whole run - catch per-recipe, log it, continue, and report
the failures list at the end (same "one dead thing doesn't kill the whole
run" principle as `check_providers.py`).

**Verify for real** against the live site before calling this phase done:
run `python scripts/import_recipes.py akis_petretzikis --limit 3`, inspect
the staged JSON files by eye, confirm the Greek and English text both read
correctly and step order matches the real recipe pages.

**Prompt:**
> Implement `backend/scripts/import_recipes.py` exactly as described above,
> wiring together every module from Phases 1-5. Run it for real against the
> live site with `--limit 3`, inspect the staged output files yourself, and
> confirm the bilingual text and step ordering look correct before stopping.
> Run the full test suite (`pytest backend/tests -q`, plus any importer
> tests you added under a suitable path) and confirm it's green. Do not
> commit - stop for review.

**Suggested commit message:** `feat: CLI entry point for importing recipes from Akis Petretzikis`

---

## After both plans land

Plan 2's developer reads `StagedRecipe` objects from
`backend/data/imported_recipes_staging/akis_petretzikis/*.json` - that
directory and that schema are the only things this plan promises to them.
Nothing in this plan writes to `backend/data/recipes.json` directly; that's
Plan 2's job, deliberately, so an import never silently becomes "live" in
the app.
