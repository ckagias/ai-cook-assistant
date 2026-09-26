import json

import pytest

from app import recipes
from app.curation.merge import export_published_json, merge_recipe
from app.schemas import Recipe, RecipeSource, RecipeStep


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "merge.db"))


def _recipe(recipe_id: str, name: str, *, url=None):
    return Recipe(
        id=recipe_id,
        name={"en": name, "el": name},
        aliases={"en": [], "el": []},
        ingredients=[name],
        steps=[RecipeStep(index=0, instruction={"en": "Do it", "el": "Κάνε το"})],
        source=RecipeSource(site="example", source_id="1", url={"en": url}, imported_at="2026-09-25T00:00:00Z") if url else None,
    )


def test_merge_appends_new_recipe_and_leaves_the_seed_untouched():
    before = recipes.all_recipes()
    merge_recipe(_recipe("cake", "Cake"))
    after = recipes.all_recipes()
    assert [r.id for r in after] == [r.id for r in before] + ["cake"]
    assert [r.model_dump() for r in after[:-1]] == [r.model_dump() for r in before]


def test_merge_replaces_existing_id_in_place():
    merge_recipe(_recipe("cake", "Cake"))
    merge_recipe(_recipe("cake", "Chocolate Cake"))
    cakes = [r for r in recipes.all_recipes() if r.id == "cake"]
    assert len(cakes) == 1 and cakes[0].name["en"] == "Chocolate Cake"


def test_publishing_from_a_staged_record_moves_the_source_and_removes_the_staged_copy():
    url = "https://example.com/recipes/cake"
    recipes.save_recipe(_recipe("s-0123abcd", "Cake", url=url), status=recipes.STAGED)
    merge_recipe(_recipe("cake", "Cake", url=url), replaces="s-0123abcd")
    assert recipes.get_recipe("s-0123abcd", status=None) is None
    assert recipes.find_source(url) == {"recipe_id": "cake", "fetched_at": None, "status": "published"}


def test_invalid_id_is_rejected_before_anything_is_written():
    count = len(recipes.all_recipes())
    with pytest.raises(ValueError, match="invalid recipe id"):
        merge_recipe(_recipe("../../etc", "Evil"))
    assert len(recipes.all_recipes()) == count


def test_export_writes_published_recipes_atomically(tmp_path):
    seed_ids = [r["id"] for r in json.loads(recipes.SEED_PATH.read_text(encoding="utf-8"))]
    merge_recipe(_recipe("cake", "Cake"))
    out = tmp_path / "export.json"
    assert export_published_json(out) == len(seed_ids) + 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [r["id"] for r in data] == [*seed_ids, "cake"]
    assert not (tmp_path / "export.json.tmp").exists()
