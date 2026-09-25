import json
from pathlib import Path
from typing import Optional

from .schemas import Recipe, RecipeStep

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "recipes.json"
_recipes: list[Recipe] = []


def load_recipes() -> list[Recipe]:
    global _recipes
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    _recipes = [Recipe.model_validate(item) for item in data]
    return _recipes


def all_recipes() -> list[Recipe]:
    if not _recipes:
        load_recipes()
    return _recipes


def get_recipe(recipe_id: str) -> Optional[Recipe]:
    for recipe in all_recipes():
        if recipe.id == recipe_id:
            return recipe
    return None


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
