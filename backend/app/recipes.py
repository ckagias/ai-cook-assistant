"""The recipe knowledge base, stored in SQLite (app/db.py).

data/recipes.json stays the version-controlled seed of hand-curated recipes; the database is
created and seeded from it on first use. Only `published` recipes are ever served to the app -
imported ones stay `staged` until a human has curated the safety-relevant fields (DESIGN.md #4).

The read functions keep their original signatures, so main.py and vision.py are unchanged.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import db
from .schemas import EquipmentItem, IngredientLine, Recipe, RecipeSource, RecipeStep, RecipeTimes

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "recipes.json"
DATA_PATH = SEED_PATH  # older name, kept for callers that still import it
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PUBLISHED = "published"
STAGED = "staged"

_ready: set[str] = set()
_vocab_cache: dict[str, tuple[str, set[str]]] = {}


def valid_id(recipe_id: str) -> bool:
    return bool(ID_PATTERN.match(recipe_id or ""))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------- setup


def ensure_ready() -> None:
    """Migrate the database and seed the curated recipes the first time a path is used."""
    path = db.db_path()
    key = str(path.resolve())
    if key in _ready:
        return
    db.migrate(path)
    with db.session(path) as conn:
        if conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0:
            seed_from_json(conn)
        indexed = conn.execute("SELECT COUNT(*) FROM recipe_search").fetchone()[0]
        if indexed != conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]:
            _rebuild_search_index(conn)  # a database from before the search index existed
    _ready.add(key)


def seed_from_json(conn: sqlite3.Connection, path: Path = SEED_PATH) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for item in data:
        save_recipe(Recipe.model_validate(item), status=PUBLISHED, conn=conn)
    return len(data)


def load_recipes() -> list[Recipe]:
    """Startup hook (main.py): make sure the database exists, then return what the app serves."""
    ensure_ready()
    return all_recipes()


# ---------------------------------------------------------------- read


def _row_to_recipe(conn: sqlite3.Connection, row: sqlite3.Row) -> Recipe:
    rid = row["id"]
    steps = [
        RecipeStep(
            index=s["idx"],
            instruction=json.loads(s["instruction_json"]),
            expected_duration_sec=s["expected_duration_sec"],
            checkable=bool(s["checkable"]),
            check_prompt_hint=s["check_prompt_hint"],
            reference_image=s["reference_image"],
            contains_raw_protein=bool(s["contains_raw_protein"]),
            section=s["section"],
            suggested_duration_sec=s["suggested_duration_sec"],
        )
        for s in conn.execute("SELECT * FROM steps WHERE recipe_id = ? ORDER BY idx", (rid,))
    ]
    details = [
        IngredientLine(
            raw_text=i["raw_text"], quantity=i["quantity"], unit=i["unit"], name=i["name"],
            group=i["group_name"], vocab_id=i["vocab_id"],
        )
        for i in conn.execute("SELECT * FROM recipe_ingredients WHERE recipe_id = ? ORDER BY position", (rid,))
    ]
    equipment = [
        EquipmentItem(name=e["name"], vocab_id=e["vocab_id"], inferred=bool(e["inferred"]))
        for e in conn.execute("SELECT * FROM recipe_equipment WHERE recipe_id = ? ORDER BY rowid", (rid,))
    ]
    src = conn.execute(
        "SELECT * FROM recipe_sources WHERE recipe_id = ? ORDER BY rowid LIMIT 1", (rid,)
    ).fetchone()
    source = None
    if src is not None:
        urls = json.loads(src["url_json"]) or {"default": src["url"]}
        source = RecipeSource(
            site=src["site"], source_id=src["source_id"] or "", url=urls,
            imported_at=src["imported_at"] or src["fetched_at"] or "", author=src["author"], fetched_at=src["fetched_at"],
        )
    times = None
    if any(row[k] is not None for k in ("prep_min", "cook_min", "total_min")):
        times = RecipeTimes(prep_min=row["prep_min"], cook_min=row["cook_min"], total_min=row["total_min"])
    # Plain ingredient strings for older clients; the structured lines are in ingredient_details.
    has_structure = any(d.quantity or d.unit or d.name or d.group or d.vocab_id for d in details)
    return Recipe(
        id=rid,
        name=json.loads(row["name_json"]),
        aliases=json.loads(row["aliases_json"]),
        ingredients=[d.raw_text for d in details],
        steps=steps,
        source=source,
        description=json.loads(row["description_json"]),
        language=row["language"],
        servings=row["servings"],
        times=times,
        difficulty=row["difficulty"],
        cuisine=row["cuisine"],
        category=row["category"],
        image_url=row["image_url"],
        video_url=row["video_url"],
        nutrition=json.loads(row["nutrition_json"]),
        dietary=json.loads(row["dietary_json"]),
        ingredient_details=details if has_structure else [],
        equipment=equipment,
    )


def all_recipes(status: Optional[str] = PUBLISHED) -> list[Recipe]:
    ensure_ready()
    with db.session() as conn:
        if status is None:
            rows = conn.execute("SELECT * FROM recipes ORDER BY rowid").fetchall()
        else:
            rows = conn.execute("SELECT * FROM recipes WHERE status = ? ORDER BY rowid", (status,)).fetchall()
        return [_row_to_recipe(conn, r) for r in rows]


def get_recipe(recipe_id: str, status: Optional[str] = PUBLISHED) -> Optional[Recipe]:
    ensure_ready()
    with db.session() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None or (status is not None and row["status"] != status):
            return None
        return _row_to_recipe(conn, row)


def get_step(recipe_id: str, step_index: int) -> Optional[RecipeStep]:
    recipe = get_recipe(recipe_id)
    if recipe is None:
        return None
    for step in recipe.steps:
        if step.index == step_index:
            return step
    return None


def reference_image_path(recipe_id: str, step_index: int) -> Optional[str]:
    step = get_step(recipe_id, step_index)
    if step is None:
        return None
    return step.reference_image


def step_contains_raw_protein(recipe_id: Optional[str], step_index: Optional[int]) -> Optional[bool]:
    # Tri-state: True/False = recipe curation overrides the model either way, None = no active recipe/step.
    if recipe_id is None or step_index is None:
        return None
    step = get_step(recipe_id, step_index)
    if step is None:
        return None
    return step.contains_raw_protein


def find_source(url: str) -> Optional[dict]:
    """Which recipe (and in what state) an imported URL already became, if any."""
    ensure_ready()
    with db.session() as conn:
        row = conn.execute(
            "SELECT s.recipe_id, s.fetched_at, r.status FROM recipe_sources s JOIN recipes r ON r.id = s.recipe_id WHERE s.url = ?",
            (url,),
        ).fetchone()
        return dict(row) if row else None


def source_payload(recipe_id: str) -> Optional[dict]:
    """The raw scraped payload a recipe was imported from."""
    ensure_ready()
    with db.session() as conn:
        row = conn.execute(
            "SELECT raw_json FROM recipe_sources WHERE recipe_id = ? ORDER BY rowid LIMIT 1", (recipe_id,)
        ).fetchone()
        return json.loads(row["raw_json"]) if row and row["raw_json"] else None


# ---------------------------------------------------------------- write


def save_recipe(
    recipe: Recipe,
    *,
    status: str,
    conn: Optional[sqlite3.Connection] = None,
    raw_source: Optional[dict] = None,
) -> None:
    """Insert or fully replace one recipe (row + steps + ingredients + equipment + source)."""
    if not valid_id(recipe.id):
        raise ValueError(f"invalid recipe id {recipe.id!r}: lowercase letters, digits, '-' and '_' only")
    if status not in (STAGED, PUBLISHED):
        raise ValueError(f"unknown status {status!r}")
    if conn is None:
        ensure_ready()
        with db.session() as own:
            return save_recipe(recipe, status=status, conn=own, raw_source=raw_source)

    times = recipe.times or RecipeTimes()
    conn.execute(
        """
        INSERT INTO recipes (id, status, name_json, aliases_json, description_json, language, servings,
                             prep_min, cook_min, total_min, difficulty, cuisine, category, image_url, video_url,
                             nutrition_json, dietary_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
            status = excluded.status, name_json = excluded.name_json, aliases_json = excluded.aliases_json,
            description_json = excluded.description_json, language = excluded.language, servings = excluded.servings,
            prep_min = excluded.prep_min, cook_min = excluded.cook_min, total_min = excluded.total_min,
            difficulty = excluded.difficulty, cuisine = excluded.cuisine, category = excluded.category,
            image_url = excluded.image_url, video_url = excluded.video_url, nutrition_json = excluded.nutrition_json,
            dietary_json = excluded.dietary_json, updated_at = excluded.updated_at
        """,
        (
            recipe.id, status, _dump(recipe.name), _dump(recipe.aliases), _dump(recipe.description),
            recipe.language, recipe.servings, times.prep_min, times.cook_min, times.total_min,
            recipe.difficulty, recipe.cuisine, recipe.category, recipe.image_url, recipe.video_url,
            _dump(recipe.nutrition), _dump(recipe.dietary), _now(),
        ),
    )

    for table in ("steps", "recipe_ingredients", "recipe_equipment"):
        conn.execute(f"DELETE FROM {table} WHERE recipe_id = ?", (recipe.id,))
    conn.executemany(
        """INSERT INTO steps (recipe_id, idx, section, instruction_json, expected_duration_sec, suggested_duration_sec,
                              checkable, check_prompt_hint, reference_image, contains_raw_protein)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (recipe.id, s.index, s.section, _dump(s.instruction), s.expected_duration_sec, s.suggested_duration_sec,
             int(s.checkable), s.check_prompt_hint, s.reference_image, int(s.contains_raw_protein))
            for s in recipe.steps
        ],
    )
    # Structured lines win when they still describe the same list the curator approved;
    # an edited plain list means the structure no longer lines up, so keep the edit.
    details = recipe.ingredient_details
    if [d.raw_text for d in details] != list(recipe.ingredients):
        details = [IngredientLine(raw_text=text) for text in recipe.ingredients]
    conn.executemany(
        """INSERT INTO recipe_ingredients (recipe_id, position, group_name, raw_text, quantity, unit, name, vocab_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(recipe.id, i, d.group, d.raw_text, d.quantity, d.unit, d.name, d.vocab_id) for i, d in enumerate(details)],
    )
    seen: set[str] = set()
    for item in recipe.equipment:
        if item.name in seen:
            continue
        seen.add(item.name)
        conn.execute(
            "INSERT INTO recipe_equipment (recipe_id, name, vocab_id, inferred) VALUES (?, ?, ?, ?)",
            (recipe.id, item.name, item.vocab_id, int(item.inferred)),
        )

    if recipe.source is not None:
        src = recipe.source
        primary = src.url.get(recipe.language or "", "") or next(iter(src.url.values()), "")
        if primary:
            conn.execute(
                """
                INSERT INTO recipe_sources (recipe_id, site, source_id, url, url_json, author, fetched_at, imported_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (url) DO UPDATE SET
                    recipe_id = excluded.recipe_id, site = excluded.site, source_id = excluded.source_id,
                    url_json = excluded.url_json, author = excluded.author, fetched_at = excluded.fetched_at,
                    imported_at = excluded.imported_at, raw_json = COALESCE(excluded.raw_json, recipe_sources.raw_json)
                """,
                (recipe.id, src.site, src.source_id, primary, _dump(src.url), src.author, src.fetched_at,
                 src.imported_at, _dump(raw_source) if raw_source is not None else None),
            )
    _index_recipe(conn, recipe)
    _vocab_cache.pop(recipe.id, None)


def publish(recipe: Recipe, *, replaces: Optional[str] = None) -> None:
    """Store a curated recipe as published. `replaces` is the staged record it was curated
    from: its source link moves over and the staged copy is removed, atomically."""
    ensure_ready()
    with db.session() as conn:
        save_recipe(recipe, status=PUBLISHED, conn=conn)
        if replaces and replaces != recipe.id:
            conn.execute("UPDATE recipe_sources SET recipe_id = ? WHERE recipe_id = ?", (recipe.id, replaces))
            conn.execute("DELETE FROM recipes WHERE id = ? AND status = ?", (replaces, STAGED))
            conn.execute("DELETE FROM recipe_search WHERE recipe_id = ?", (replaces,))
    _vocab_cache.pop(recipe.id, None)


def delete_recipe(recipe_id: str) -> bool:
    ensure_ready()
    with db.session() as conn:
        deleted = conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,)).rowcount > 0
        conn.execute("DELETE FROM recipe_search WHERE recipe_id = ?", (recipe_id,))
    _vocab_cache.pop(recipe_id, None)
    return deleted


# ---------------------------------------------------------------- search (BM25)


def _search_text(recipe: Recipe) -> str:
    from .detection.vocab_match import fold

    parts = [*recipe.name.values(), *recipe.description.values(), *recipe.ingredients,
             *(e.name for e in recipe.equipment), recipe.category or "", recipe.cuisine or ""]
    parts += [alias for values in recipe.aliases.values() for alias in values]
    return fold(" ".join(p for p in parts if p))


def _index_recipe(conn: sqlite3.Connection, recipe: Recipe) -> None:
    conn.execute("DELETE FROM recipe_search WHERE recipe_id = ?", (recipe.id,))
    conn.execute("INSERT INTO recipe_search (recipe_id, body) VALUES (?, ?)", (recipe.id, _search_text(recipe)))


def _rebuild_search_index(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM recipe_search")
    for row in conn.execute("SELECT * FROM recipes").fetchall():
        _index_recipe(conn, _row_to_recipe(conn, row))


def _stem_tokens(word: str) -> list[str]:
    from .detection.vocab_match import fold

    tokens: list[str] = []
    for token in re.findall(r"\w+", fold(word or "")):
        if len(token) < 2:
            continue
        tokens.append(token)
        # English plurals
        if token.endswith("ies") and len(token) > 4:
            tokens.append(token[:-3] + "y")
        elif token.endswith("es") and len(token) > 4:
            tokens.append(token[:-2])
        elif token.endswith("s") and len(token) > 3:
            tokens.append(token[:-1])
        # Greek inflectional endings
        if token.endswith(("ια", "ες", "ων", "ους", "ατα", "δες")) and len(token) > 4:
            tokens.append(token[:-2])
        elif token.endswith(("α", "η", "ο", "ι", "υ", "ε", "ς")) and len(token) > 3:
            stem = token[:-1]
            tokens.extend([stem, stem + "α", stem + "ο", stem + "ι", stem + "ης", stem + "ου", stem + "ες"])
    return tokens


def search_recipes(words: list[str], limit: int = 5) -> list[Recipe]:
    """Published recipes matching any of `words`, best first (SQLite FTS5 BM25). Words are
    accent-folded and matched by stem/prefix, so "αυγά" finds "αυγό" and "eggs" finds "egg"."""
    from .detection.vocab_match import fold

    tokens: list[str] = []
    for word in words:
        tokens.extend(_stem_tokens(word))
    if not tokens:
        return []

    unique_tokens = list(dict.fromkeys(tokens))
    # For words of length >= 4, allow prefix match; for short stems (e.g. "egg", "αυγ") use exact tokens
    query_parts = []
    for t in unique_tokens:
        if len(t) >= 4:
            query_parts.append(f'"{t}"*')
        else:
            query_parts.append(f'"{t}"')
    query = " OR ".join(dict.fromkeys(query_parts))

    ensure_ready()
    with db.session() as conn:
        rows = conn.execute(
            """SELECT r.* FROM recipe_search JOIN recipes r ON r.id = recipe_search.recipe_id
               WHERE recipe_search MATCH ? AND r.status = ? ORDER BY bm25(recipe_search) LIMIT ?""",
            (query, PUBLISHED, limit),
        ).fetchall()
        return [_row_to_recipe(conn, row) for row in rows]


# ---------------------------------------------------------------- detection link


def detection_vocabulary(recipe_id: str) -> Optional[set[str]]:
    """Detector classes relevant to one recipe: the always-on base set (hands, core cookware,
    hazards), the classes its ingredients/equipment were linked to at import, and whatever its
    text mentions. None = unknown recipe, so /detect falls back to the full vocabulary rather
    than silently showing nothing. Cached per recipe version - /detect asks on every frame."""
    from .detection.vocab_match import match_classes
    from .detection.vocabulary import load_vocabulary

    ensure_ready()
    with db.session() as conn:
        row = conn.execute("SELECT updated_at FROM recipes WHERE id = ? AND status = ?", (recipe_id, PUBLISHED)).fetchone()
    if row is None:
        return None
    cached = _vocab_cache.get(recipe_id)
    if cached and cached[0] == row["updated_at"]:
        return set(cached[1])

    recipe = get_recipe(recipe_id)
    if recipe is None:
        return None
    linked = {d.vocab_id for d in recipe.ingredient_details if d.vocab_id} | {e.vocab_id for e in recipe.equipment if e.vocab_id}
    texts = [*recipe.name.values(), *recipe.ingredients, *(e.name for e in recipe.equipment)]
    texts += [text for step in recipe.steps for text in step.instruction.values()]
    vocab = load_vocabulary()
    allowed = vocab.base_ids() | {v for v in linked if vocab.by_id(v)} | match_classes(texts)
    _vocab_cache[recipe_id] = (row["updated_at"], allowed)
    return set(allowed)
