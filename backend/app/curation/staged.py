from __future__ import annotations

import json
from pathlib import Path

from app.importers.schema import StagedIngredient, StagedMetadata, StagedRecipe, StagedStep
from app.schemas import Recipe

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


# --- staged records in the database (the generic any-URL importer writes these) ---


def list_staged_records() -> list[Recipe]:
    from app import recipes as recipes_module

    return recipes_module.all_recipes(status=recipes_module.STAGED)


def staged_from_record(record: Recipe) -> StagedRecipe:
    """Adapt a staged database record to the shape run_curation() works on."""
    lang = record.language or "en"
    source = record.source
    if record.ingredient_details:
        ingredients = [
            StagedIngredient(title={lang: d.raw_text}, quantity=d.quantity or "", unit={lang: d.unit} if d.unit else {})
            for d in record.ingredient_details
        ]
    else:
        ingredients = [StagedIngredient(title={lang: text}) for text in record.ingredients]
    times = record.times
    return StagedRecipe(
        source=source.site if source else "unknown",
        source_id=source.source_id if source else record.id,
        source_url=source.url if source else {},
        fetched_at=(source.fetched_at or source.imported_at) if source else "",
        title=record.name,
        category={"title": record.category} if record.category else {},
        ingredients=ingredients,
        steps=[
            StagedStep(section={lang: s.section} if s.section else {}, text=s.instruction,
                       suggested_duration_sec=s.suggested_duration_sec)
            for s in record.steps
        ],
        metadata=StagedMetadata(
            make_time_min=times.prep_min if times else None,
            bake_time_min=times.cook_min if times else None,
            servings=record.servings,
            difficulty=record.difficulty,
            dietary_flags=record.dietary,
            equipment=[e.name for e in record.equipment],
            image_url=record.image_url,
            video_url=record.video_url,
        ),
    )
