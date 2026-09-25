from __future__ import annotations

import json
from pathlib import Path

from app.importers.schema import StagedRecipe

STAGING_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "imported_recipes_staging"


def _staging_dir(source: str | None = None) -> Path:
    root = STAGING_ROOT if source is None else STAGING_ROOT / source
    return root


def list_staged(source: str | None = None) -> list[StagedRecipe]:
    """Load every staged recipe JSON file from the staging tree."""
    root = _staging_dir(source)
    if not root.exists():
        return []

    recipes: list[StagedRecipe] = []
    candidates = sorted(root.glob("*.json")) if source is not None else sorted(STAGING_ROOT.glob("**/*.json"))
    for path in candidates:
        if path.name == "manifest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            recipes.append(StagedRecipe.model_validate(data))
        except Exception as exc:  # pragma: no cover - defensive guard for noisy failures
            raise ValueError(f"Invalid staged recipe file: {path} ({exc})") from exc
    return recipes


def get_staged(source: str, source_id: str) -> StagedRecipe | None:
    """Return one staged recipe by source and source_id, or None if absent."""
    for recipe in list_staged(source):
        if recipe.source_id == source_id:
            return recipe
    return None
