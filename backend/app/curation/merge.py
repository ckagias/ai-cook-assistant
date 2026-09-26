from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from app import recipes as recipes_module
from app.schemas import Recipe


def merge_recipe(recipe: Recipe, *, replaces: Optional[str] = None) -> None:
    """Publish a curated recipe into the database. Replaces a recipe with the same id in place
    (the curation workflow refuses accidental id collisions before this point). `replaces` is
    the staged record it was curated from, which is removed in the same transaction."""
    recipes_module.publish(recipe, replaces=replaces)


# Optional metadata added with the database; omitted from the export when empty so the three
# original hand-written recipes keep exactly their original keys.
_OPTIONAL_RECIPE_KEYS = (
    "source", "description", "language", "servings", "times", "difficulty", "cuisine", "category",
    "image_url", "video_url", "nutrition", "dietary", "ingredient_details", "equipment",
)
_OPTIONAL_STEP_KEYS = ("section", "suggested_duration_sec")


def _export_shape(recipe: Recipe) -> dict:
    data = recipe.model_dump(mode="json")
    for key in _OPTIONAL_RECIPE_KEYS:
        if not data.get(key):
            data.pop(key, None)
    for step in data["steps"]:
        for key in _OPTIONAL_STEP_KEYS:
            if step.get(key) is None:
                step.pop(key, None)
    return data


def export_published_json(path: Path = recipes_module.SEED_PATH) -> int:
    """Write every published recipe back to a JSON file (e.g. data/recipes.json, to commit
    newly curated recipes as part of the seed). Atomic: a temp file then os.replace, so a
    crash mid-write can't leave the file truncated. Returns the number of recipes written."""
    published = recipes_module.all_recipes()
    payload = [_export_shape(r) for r in published]
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp_path = Path(path).with_suffix(Path(path).suffix + ".tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    os.replace(tmp_path, path)
    return len(published)
