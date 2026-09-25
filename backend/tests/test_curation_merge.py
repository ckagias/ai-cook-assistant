import json

import pytest

from app.curation.merge import merge_recipe
from app.schemas import Recipe, RecipeStep


def _recipe(recipe_id: str, name: str, *, ingredients=None):
    return Recipe(
        id=recipe_id,
        name={"en": name, "el": name},
        aliases={"en": [], "el": []},
        ingredients=ingredients or [name],
        steps=[
            RecipeStep(
                index=0,
                instruction={"en": "Do it", "el": "Κάνε το"},
                expected_duration_sec=None,
                checkable=False,
                check_prompt_hint=None,
                reference_image=None,
                contains_raw_protein=False,
            )
        ],
    )


def test_merge_recipe_appends_new_recipe(tmp_path):
    path = tmp_path / "recipes.json"
    existing = [_recipe("pasta", "Pasta")]
    path.write_text(json.dumps([existing[0].model_dump(mode="python")], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    merge_recipe(_recipe("cake", "Cake"), path=path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [item["id"] for item in payload] == ["pasta", "cake"]


def test_merge_recipe_replaces_existing_id(tmp_path):
    path = tmp_path / "recipes.json"
    first = _recipe("cake", "Cake")
    second = _recipe("cake", "Chocolate Cake")
    path.write_text(json.dumps([first.model_dump(mode="python")], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    merge_recipe(second, path=path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["id"] == "cake"
    assert payload[0]["name"]["en"] == "Chocolate Cake"


def test_merge_recipe_validates_before_writing(tmp_path, monkeypatch):
    path = tmp_path / "recipes.json"
    original = json.dumps([_recipe("pasta", "Pasta").model_dump(mode="python")], ensure_ascii=False, indent=2) + "\n"
    path.write_text(original, encoding="utf-8")

    recipe = _recipe("cake", "Cake")
    real_validate = Recipe.model_validate

    def boom(value):
        raise ValueError("validation failed")

    monkeypatch.setattr(Recipe, "model_validate", staticmethod(boom))
    with pytest.raises(ValueError, match="validation failed"):
        merge_recipe(recipe, path=path)

    assert path.read_text(encoding="utf-8") == original
