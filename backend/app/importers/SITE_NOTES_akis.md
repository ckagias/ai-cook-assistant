# Site notes: akispetretzikis.com

Re-verified 2026-09-25 against the live site (browser, after a non-browser
fetch was challenged). These notes are the working reference for later
importer phases. Compare against `plans/PLAN_IMPORT_AKIS.md` "Ground truth".

## robots.txt

`GET https://akispetretzikis.com/robots.txt` — **unchanged** from the plan.

```
User-agent: *
Allow: /

User-agent: googlebot
Allow: /
Disallow: /assets/*
Disallow: /icons/*

User-agent: Google-InspectionTool
Allow: /
Disallow: /assets/*
Disallow: /icons/*
```

Crawling recipe pages and the sitemap is allowed for a generic user-agent.
`/assets/*` and `/icons/*` only matter for Googlebot.

## Cloudflare / User-Agent

Still present, and stricter than "bare UA → 403" in one important way:

- A non-browser HTTP client (Cursor `WebFetch`) received a **Cloudflare
  JavaScript challenge interstitial** ("Performing security verification…
  Enable JavaScript and cookies to continue"), not the recipe HTML and not
  a plain JSON 403 body.
- A real Chromium session loaded the same URLs successfully and exposed
  `__NEXT_DATA__`.

Implications for Phase 2: a desktop Chrome `User-Agent` is still required
(as the plan says). Treat **403 and challenge/interstitial HTML** as
retryable. A fetch that "succeeds" with HTTP 200 but whose body has no
`__NEXT_DATA__` (challenge page) must be treated as failure, not as a
missing recipe. Do not try to solve the JS challenge; retry with backoff
like Wikimedia 429 handling in `fetch_reference_candidates.py`.

## Page shape (Next.js)

Confirmed on recipe **2555**:

- `<script id="__NEXT_DATA__" type="application/json">` is present.
- Recipe payload path is still `props.pageProps.ssRecipe.data`.
- `buildId` observed: `9eox-6PDlL__v1lp64E5i` (will change on deploys;
  do not hard-code it).

You do not need CSS/HTML scraping of the visible page.

## Recipe URLs

Still:

- Greek (default locale): `https://akispetretzikis.com/recipe/<id>/<slug>`
- English: `https://akispetretzikis.com/en/recipe/<id>/<slug>`

Same numeric `id` for both. Sample:

- EL title: `Κοτόπουλο λεμονάτο με πατάτες`
- EN title: `Greek lemon roast chicken and potatoes`

English is **native copy**, not a machine calque of the Greek (titles
differ; potato-prep steps differ in substance: EL leaves the skin on,
EN peels and cuts wedges).

Next.js still resolves by id; the slug in the URL does not have to be
guessed if you only have an id (Phase 4: fetch `/recipe/{id}/x` and read
`slug` back from `__NEXT_DATA__`).

## Sitemap

`https://akispetretzikis.com/sitemap.xml` is still a **single flat
`<urlset>`**, not a sitemap index.

| Metric (2026-09-25) | Count | vs plan |
|---|---|---|
| `<loc>` entries | 14,212 | same as planning |
| Default-locale `…/recipe/<digits>/<slug>` | 5,374 | same |
| Unique ids in that default-locale set | 5,374 | no id duplication in this form |
| `/en/recipe/<id>/…` locs | 5,381 | **not called out in the plan** |

Non-recipe locs include the homepage and `/blog/…` (and, per the plan,
category pages). Sample default-locale recipe locs:

- `https://akispetretzikis.com/recipe/1006/peinirli-sokolatas`
- `https://akispetretzikis.com/recipe/102/pagwto-pralina-sokolatas`

Phase 3 should keep filtering to the **default-locale** recipe regex only,
then fetch `/en/` by constructing the URL from the id. Do not treat `/en/`
sitemap entries as extra recipes.

## `__NEXT_DATA__` fields on `ssRecipe.data` (recipe 2555)

Present and matching the plan's list: `id`, `slug`, `title`, `video_url`,
`method`, `ingredient_sections`, `make_time`, `bake_time`, `shares`,
`difficulty`, `nutrition`, dietary `is_*` flags, `equipment_used`,
`assets`, `category`.

Details that affect later phases:

- **`method`**: list of `{section, steps: [{id, step}]}`. Step HTML still
  carries entities and tags, e.g. `200&deg;C`, `<strong>&nbsp;</strong>`,
  `<strong>.</strong>`. `strip_html` in Phase 4 is required.
- **`ingredient_sections`**: `{title, ingredients: [{title, unit,
  quantity, info, conversions, …}]}`. `unit` can be `""`. `info` can be
  `"μεσαίες "` / `"medium sized "`.
- **`shares`**: still a string range, `"4-6"` — do not coerce to int.
- **`make_time` / `bake_time`**: integers (minutes), here `25` and `90`.
- **Dietary flags**: `is_ve`, `is_vg`, `is_gf`, `is_df`, `is_ef`, `is_nf`
  plus extras **`is_ls`** and **`is_sf`** (0/1 ints, not JSON booleans).
  Phase 5 maps the documented six to English keys; `is_ls` / `is_sf` are
  unused by that schema unless Plan 2 asks for them.
- **`equipment_used`**: list of **objects** `{ "title": "Τηγάνι" }`, not
  bare strings. Normalize to strings in Phase 5.
- **`assets`**: image objects with `host` + `url` (absolute JPEG URLs).
- **`category`**: `{id, slug, parent_id, depth, …}` — **no category title
  in this object**. For 2555: `id=21`, `slug="kotopulo"`. Phase 5's
  `title_el` / `title_en` cannot be filled from `category` alone; leave
  empty or resolve from a category listing later.
- **`nutrition`**: `{nutrition_per, sections}` (richer than we stage).

## EL vs EN structure — **does not always zip 1:1**

The plan assumed Greek and English `method` / `ingredient_sections` share
the same structural order. On **2555 they do not**:

| Piece | Greek | English |
|---|---|---|
| method section 1 (potatoes) | 5 steps | 6 steps |
| method section 3 (chicken) | 7 steps | 8 steps |
| ingredient section titles | 4 named sections | 3rd title is `""`; "For the chicken" missing as a title |
| `difficulty` | `"Εύκολη"` | `null` |
| `video_url` | `youtube.com/watch?v=wzM9whpShe8` | `youtube.com/watch?v=OK2pJl-hY3k` |

Section *labels* still line up (Let's get cooking / potatoes / marinade /
chicken). Step **counts** inside a section can differ. Phase 5's
position-zip must not assume equal list lengths — pad, pair by section
name, or record a mismatch rather than silently dropping steps.

Re-check this on a few more recipes in Phase 5 before locking the zip
strategy.

## Third-party scrapers

Not used. Fetch the site directly.

## Sample URLs used for this pass

- `https://akispetretzikis.com/robots.txt`
- `https://akispetretzikis.com/recipe/2555/kotopoylo-lemonato-me-patates`
- `https://akispetretzikis.com/en/recipe/2555/kotopoylo-lemonato-me-patates`
- `https://akispetretzikis.com/sitemap.xml`
