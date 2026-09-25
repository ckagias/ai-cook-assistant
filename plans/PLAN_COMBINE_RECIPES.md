# Combine plan: curate and merge imported recipes into the app, phase by phase

**Branch:** `feature/combine-recipes`
**Owner:** Developer B
**Depends on:** the staged JSON contract from `PLAN_IMPORT_AKIS.md` Phase 5
(`StagedRecipe`, written to
`backend/data/imported_recipes_staging/<source>/*.json`). You do not need
Plan 1's actual scraping code to build or test this plan - write a handful
of fixture `StagedRecipe` JSON files by hand (matching the schema below)
and develop against those. Swap in real staged output from Plan 1 whenever
it's ready.
**Feeds:** `backend/data/recipes.json`, the app's live recipe knowledge
base.

This is a developer/admin CLI tool, same spirit as
`scripts/add_reference.py`: a person runs it, reviews and edits what it
proposes, and nothing becomes usable by the app until a human has
confirmed the safety-relevant fields. There is no end-user-facing "browse
imported recipes" UI in this MVP.

> **Security review required before merge.** This plan (together with
> `PLAN_IMPORT_AKIS.md`) introduces the first untrusted external content
> this codebase has ever had to parse. Before this branch merges, run this
> repo's `security-review` skill (or an equivalent manual pass) against it,
> specifically checking: the parsing of staged JSON never `eval`s/execs
> anything from it, there are no SSRF-shaped fetches, and there is no
> path-traversal risk in how staged filenames are derived from source data
> (`source_id` used directly in a file path - confirm it's validated as
> safe, e.g. digits-only, before ever touching the filesystem). See
> `plans/PLAN_SECURITY_NETWORK_HARDENING.md` Phase 6.

Each phase below is self-contained: what to build and why, a ready-to-paste
prompt, and a suggested commit message. Feed one phase's prompt at a time to
the LLM, review the diff, commit yourself (the LLM should never run `git
commit`), then move to the next phase.

---

## Why this can't be fully automatic

The app's safety design (see `DESIGN.md` #4 in this repo) depends on every
recipe's safety-relevant fields being a **deliberate human decision**, not
an inference:

- `contains_raw_protein` per step. The existing pancakes recipe curates
  step 2 as `contains_raw_protein: false` **even though the batter contains
  raw egg**, because a vision model correctly flagging that would trigger
  "use a meat thermometer" advice on a pancake - useless and wrong. An
  automated classifier (or a naive "does the ingredient list mention
  chicken/egg/fish?" heuristic) cannot make that judgment call. A source
  recipe's own raw-handling warnings (e.g. one real Akis chicken recipe's
  step text: *"It is better to wear disposable gloves when working with
  raw chicken"*) are a strong **signal**, not a substitute for a person
  deciding which of the app's (coarser) steps that risk actually applies
  to.
- **Step granularity mismatch.** A source recipe's instructions are much
  finer-grained than what this app wants as a `RecipeStep` - the existing
  pasta recipe has one step "Add the pasta and cook until tender" covering
  what a source site might split into "add the pasta", "stir once",
  "check every two minutes", "taste a piece". Grouping fine-grained source
  instructions into the handful of coarse, checkable/timed steps this app
  actually uses is an editorial decision, not a parsing problem.
- `checkable`, `expected_duration_sec`, `check_prompt_hint` all describe
  what the *voice assistant* should do at that step, which has no
  equivalent field on the source site at all.

So this plan's job is: read what Plan 1 staged, present it to a human in a
form that makes good decisions fast, and only then write to
`recipes.json`.

---

## The staged schema this plan reads (defined in `PLAN_IMPORT_AKIS.md` Phase 5)

Restated here for convenience - the two plans must stay in sync on this
shape; if you need a field Plan 1 doesn't provide, that's a conversation
with Plan 1's developer, not a workaround here.

```python
class StagedIngredient(BaseModel):
    title: dict[str, str]          # {"el": ..., "en": ...}
    quantity: str = ""
    unit: dict[str, str] = {}
    info: dict[str, str] = {}

class StagedStep(BaseModel):
    section: dict[str, str]        # the site's own loose grouping
    text: dict[str, str]           # {"el": ..., "en": ...}, HTML-stripped

class StagedMetadata(BaseModel):
    make_time_min: int | None = None
    bake_time_min: int | None = None
    servings: str | None = None
    difficulty: str | None = None
    dietary_flags: dict[str, bool] = {}
    equipment: list[str] = []
    image_url: str | None = None
    video_url: str | None = None

class StagedRecipe(BaseModel):
    source: str                    # "akis_petretzikis"
    source_id: str
    source_url: dict[str, str]
    fetched_at: str
    title: dict[str, str]
    category: dict[str, str] = {}
    ingredients: list[StagedIngredient]
    steps: list[StagedStep]        # flat, in source order, NOT grouped yet
    metadata: StagedMetadata
```

Import it directly from Plan 1's module
(`backend/app/importers/schema.py`) rather than redefining it - Plan 1
lands this file regardless of which plan merges first, since neither plan
depends on the other's branch to build.

---

## Phase 1 — Extend the recipe schema with source tracking

**Files:** `backend/app/schemas.py`.

Every recipe gets an optional provenance record, so a future import from a
*different* site can detect "this might already exist" and so a re-run of
this plan's import for the *same* source recipe is idempotent (update, not
duplicate). Backward compatible: the existing 3 hand-authored recipes
(pasta, pancakes, scrambled_eggs) simply have `source: None`.

```python
class RecipeSource(BaseModel):
    site: str                  # "akis_petretzikis" - matches StagedRecipe.source
    source_id: str
    url: dict[str, str]        # {"el": ..., "en": ...}
    imported_at: str           # ISO 8601 UTC timestamp of curation, not the original fetch

class Recipe(BaseModel):
    id: str
    name: dict[str, str]
    aliases: dict[str, list[str]]
    ingredients: list[str]
    steps: list[RecipeStep]
    source: Optional[RecipeSource] = None
```

Confirm `recipes.py`'s loader and every existing test in `test_smoke.py`
still pass unchanged - this must be a strictly additive, optional field.

**Prompt:**
> Extend `backend/app/schemas.py` with the `RecipeSource` model and the new
> optional `source` field on `Recipe`, exactly as specified above. Do not
> change `recipes.json` or any existing recipe data in this phase. Run
> `pytest backend/tests -q` and confirm every existing test still passes
> unchanged - this field must be purely additive. Do not commit - stop for
> review.

**Suggested commit message:** `feat: add optional source provenance to the Recipe schema`

---

## Phase 2 — Staged-import reader

**Files:** `backend/app/curation/__init__.py`, `backend/app/curation/staged.py`.

```python
STAGING_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "imported_recipes_staging"

def list_staged(source: str | None = None) -> list[StagedRecipe]:
    # Walk STAGING_ROOT (or STAGING_ROOT/<source> if given), load every
    # *.json that isn't manifest.json, validate against StagedRecipe.
    # A file that fails validation is a loud error naming the file, not a
    # silent skip - a corrupt staged file usually means Plan 1's normalizer
    # has a bug worth knowing about immediately, not quietly losing a recipe.

def get_staged(source: str, source_id: str) -> StagedRecipe | None:
    # Single-recipe lookup, used by Phase 3's curation flow.
```

**Prompt:**
> Implement `backend/app/curation/staged.py` exactly as described above,
> importing `StagedRecipe` from `backend/app/importers/schema.py` (Plan
> 1's module - if it doesn't exist on this branch yet, stub an identical
> copy here with a comment noting it must be deleted and re-imported from
> Plan 1's module at merge time, so development isn't blocked on branch
> order). Write tests using a handful of hand-written fixture StagedRecipe
> JSON files (in a test fixtures directory, not the real staging path)
> covering: list_staged returns all of them, list_staged filters by
> source, get_staged finds one by id and returns None for an unknown one,
> and a corrupt fixture file raises a clear error naming the file. Do not
> commit - stop for review.

**Suggested commit message:** `feat: read staged imported recipes`

---

## Phase 3 — Curation workflow

**Files:** `backend/scripts/curate_recipe.py`, `backend/app/curation/workflow.py`.

The core editorial tool. One staged recipe in, one `Recipe` (app schema)
out, via an interactive terminal session - not a GUI, not a web form,
consistent with every other admin tool in this repo.

```
Usage: python scripts/curate_recipe.py <source> <source_id> [--out-id <recipe-id>]
Example: python scripts/curate_recipe.py akis_petretzikis 2555
```

Flow (`workflow.py:run_curation(staged: StagedRecipe) -> Recipe`):

1. **Print the full staged recipe** - title (both languages), category,
   servings/times, every ingredient, every flat source step in order with
   its section header. This is the human's only view into the source
   material, so show everything, not a truncated summary.
2. **Propose a recipe id**: slugify the English title, check it doesn't
   collide with an existing `recipes.json` id; if it does, ask for one.
3. **Ingredient pass**: show the staged ingredients (already bilingual);
   let the curator accept as-is or edit the flattened `ingredients:
   list[str]` the app schema actually wants (the app's ingredient list is
   just display strings, not structured quantity/unit data - staged
   ingredients carry more detail than the app currently uses, and that's
   fine, it's still in the staged JSON file for later if the schema grows).
4. **Step-grouping pass** - the important one:
   - Show the flat staged steps, numbered.
   - Ask the curator to group them into app steps by entering index ranges
     (e.g. `1-3`, then `4`, then `5-8`) until every staged step is
     assigned to exactly one group, in order. Refuse to proceed if any
     staged step is left ungrouped or double-assigned.
   - For each resulting group, ask: the step's instruction text in each
     language (default: staged steps' text joined with a space, editable),
     whether it's `checkable`, `expected_duration_sec` (blank = None),
     `check_prompt_hint` (only if checkable), and **explicitly and
     separately** `contains_raw_protein` (default to `False`, never
     inferred from ingredient text - the curator must affirmatively set
     this, since a defaulted-True on every meat recipe would make the
     protein-safety override fire on nearly everything and defeat its own
     purpose, exactly the pancake-batter lesson in reverse).
     - If a source ingredient list or step text mentions a common raw
       protein term (chicken, pork, beef, fish, egg, etc. - a short
       hardcoded list, not an ML classifier), print a one-line hint next to
       the prompt (e.g. "note: this recipe's ingredients include
       'chicken'") - a nudge for the curator to consider, never a default
       value.
   - `reference_image` is left `None` here - installing one is
     `add_reference.py`'s job (already built, don't rebuild it); print a
     reminder at the end listing which steps were marked checkable and
     therefore might want one.
5. **Print the resulting `Recipe` object** and ask for final confirmation
   before returning it.

**Prompt:**
> Implement `backend/app/curation/workflow.py`'s `run_curation()` and the
> `backend/scripts/curate_recipe.py` CLI entry point exactly as described
> above. Use `input()` for the interactive prompts (no new TUI dependency).
> Write tests for `run_curation()` that supply canned input via a mocked
> input function (not real stdin), covering: a full happy-path curation
> producing a valid `Recipe`, refusing to proceed when a staged step is
> left ungrouped, refusing when a step is assigned to two groups, and
> `contains_raw_protein` defaulting to False and requiring an explicit
> answer rather than being inferred. Do not commit - stop for review.

**Suggested commit message:** `feat: interactive curation workflow for staged recipes`

---

## Phase 4 — Cross-source duplicate detection

**Files:** `backend/app/curation/dedupe.py`.

Designed for multiple sources from the start, even though only Akis exists
today - so adding site #2 later doesn't mean reworking this.

```python
def find_possible_duplicates(candidate_title: dict[str, str], existing: list[Recipe]) -> list[Recipe]:
    # Normalize (casefold, strip accents/tones on Greek text, collapse
    # whitespace) candidate_title's "el" and "en" values and every existing
    # recipe's name + aliases the same way. Flag a match on exact equality
    # OR a high token-overlap ratio (e.g. simple set-intersection-over-union
    # on whitespace-split words above some threshold - no new NLP/fuzzy-
    # matching dependency needed for this). This is a prompt for a human,
    # not an automatic merge or reject - return the candidates, let Phase 5
    # decide what to do with them.
```

This runs as part of Phase 3's curation flow (after the id/title is
settled, before final confirmation): if `find_possible_duplicates` returns
anything, show the matches (id, name, source) and ask the curator to
choose: **new recipe anyway** / **update the existing recipe's steps
instead** (replaces its `steps`/`ingredients`, keeps its `id`) / **abort**.

**Prompt:**
> Implement `backend/app/curation/dedupe.py`'s `find_possible_duplicates()`
> exactly as described above (normalized exact match OR token-overlap
> threshold, no new dependency), and wire the three-way prompt
> (new/update/abort) into Phase 3's `run_curation()` flow. Write tests
> covering: an exact-title match is found, a near-duplicate with different
> word order/casing is found via token overlap, an unrelated recipe is not
> flagged, and each of the three curator choices produces the right
> outcome (a brand new Recipe, an existing Recipe with updated
> steps/ingredients but the same id, or None on abort). Do not commit -
> stop for review.

**Suggested commit message:** `feat: cross-source duplicate detection during curation`

---

## Phase 5 — Merge into recipes.json

**Files:** `backend/app/curation/merge.py`.

```python
def merge_recipe(recipe: Recipe, *, path: Path = recipes.DATA_PATH) -> None:
    # Load the current recipes.json as a list of dicts. If recipe.id matches
    # an existing entry, replace it in place (preserves list order); else
    # append. Validate the FULL resulting list against Recipe before writing
    # anything - one bad recipe must not corrupt the file that the other N
    # recipes already live in safely. Write atomically: serialize to a
    # temp file in the same directory, then os.replace() over the real
    # path, so a crash mid-write can't leave recipes.json truncated.
    # ensure_ascii=False (Greek text), indent=2, trailing newline - match
    # the existing file's own formatting exactly (diff it before writing
    # to confirm untouched recipes produce a zero-diff).
```

Call this from the end of `curate_recipe.py` (Phase 3) once curation
produces a confirmed `Recipe`. Print the exact path written and a reminder
of any reference-image gaps flagged in Phase 3.

**Verify for real**: run the full curation CLI against a real (or
hand-written fixture) staged recipe end-to-end, inspect the resulting
`recipes.json` diff by eye, and confirm `GET /recipes` and
`GET /recipes/{id}` serve the new recipe correctly through the running app.

**Prompt:**
> Implement `backend/app/curation/merge.py`'s `merge_recipe()` exactly as
> described above (in-place replace on id match, append otherwise,
> validate the full resulting list before writing, atomic write, matching
> existing file formatting exactly) and call it from the end of
> `curate_recipe.py`. Write tests covering: appending a new recipe leaves
> existing recipes byte-for-byte unchanged, replacing an existing id
> updates only that entry, and a write that would fail schema validation
> raises before touching the file on disk at all (verify the file is
> unmodified after a failed attempt). Then run the full curation CLI
> end-to-end against a real or hand-written fixture staged recipe, inspect
> the resulting `recipes.json` diff yourself, start the backend, and
> confirm `GET /recipes` and `GET /recipes/{id}` serve it correctly. Run
> `pytest backend/tests -q` and confirm everything is still green. Do not
> commit - stop for review.

**Suggested commit message:** `feat: merge curated recipes into recipes.json`

---

## Phase 6 — Full regression pass

**Files:** none (verification only).

Before considering this plan done: run the complete backend test suite,
confirm the 3 original demo recipes are byte-for-byte untouched in
`recipes.json` (unless you deliberately curated an update to one), and
manually walk through `/analyze` for a newly-merged recipe's checkable step
in `DEMO_MODE` to confirm the safety rules (`_apply_protein_safety`,
`_apply_safety_flag`) still run identically over it - they read `Recipe`/
`RecipeStep` fields, not anything source/import-specific, so this should
need no code changes, but prove it rather than assume it.

**Prompt:**
> Run `pytest backend/tests -q` and confirm it's fully green. Confirm
> `backend/data/recipes.json`'s three original recipes (pasta, pancakes,
> scrambled_eggs) are unchanged unless you deliberately updated one via
> this plan's dedupe/update path. Start the backend, pick one newly-merged
> checkable step, and walk it through `/analyze` (real or `DEMO_MODE`) to
> confirm `_apply_protein_safety` and `_apply_safety_flag` in `main.py`
> apply to it exactly as they do to the original three recipes. Report
> what you found - this phase is verification, not new code, so there's
> nothing to commit unless it surfaces a bug.

**Suggested commit message:** (none expected - fix commits only if this phase finds a bug)
