from __future__ import annotations

import json
import os
from pathlib import Path

from app import recipes as recipes_module
from app.schemas import Recipe


def merge_recipe(recipe: Recipe, *, path: Path = recipes_module.DATA_PATH) -> None:
    """Append or replace a recipe in recipes.json using an atomic write."""
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[Recipe] = []
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"recipes file is not a list: {path}")
        existing = [Recipe.model_validate(item) for item in data]

    merged = [r.model_dump(mode="python") for r in existing]
    replaced = False
    for idx, current in enumerate(merged):
        if current["id"] == recipe.id:
            merged[idx] = recipe.model_dump(mode="python")
            replaced = True
            break
    if not replaced:
        merged.append(recipe.model_dump(mode="python"))

    validated = [Recipe.model_validate(item) for item in merged]
    payload = [r.model_dump(mode="python", exclude_none=False) for r in validated]
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if not serialized.endswith("\n"):
        serialized += "\n"

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    os.replace(tmp_path, path)

    return None
