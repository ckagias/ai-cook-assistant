import json
import sqlite3

import pytest

from app import db, recipes
from app.schemas import EquipmentItem, IngredientLine, Recipe, RecipeSource, RecipeStep, RecipeTimes


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    path = tmp_path / "cook.db"
    monkeypatch.setenv("DB_PATH", str(path))
    return path


def test_first_use_migrates_and_seeds_from_recipes_json(fresh_db):
    ids = [r.id for r in recipes.all_recipes()]
    seed = json.loads(recipes.SEED_PATH.read_text(encoding="utf-8"))
    assert ids == [r["id"] for r in seed]
    # The seeded recipes round-trip exactly - the API output for them is unchanged.
    for item, recipe in zip(seed, recipes.all_recipes()):
        assert Recipe.model_validate(item).model_dump() == recipe.model_dump()


def test_migrations_are_idempotent(fresh_db):
    recipes.ensure_ready()
    assert db.migrate(fresh_db) == []
    seed = json.loads(recipes.SEED_PATH.read_text(encoding="utf-8"))
    with db.session(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == len(seed)


def test_staged_recipes_are_never_served():
    recipes.save_recipe(
        Recipe(id="s-1", name={"en": "Imported"}, aliases={}, ingredients=["x"],
               steps=[RecipeStep(index=0, instruction={"en": "Do"})]),
        status=recipes.STAGED,
    )
    assert "s-1" not in [r.id for r in recipes.all_recipes()]
    assert recipes.get_recipe("s-1") is None
    assert recipes.get_recipe("s-1", status=None) is not None
    assert recipes.step_contains_raw_protein("s-1", 0) is None  # /analyze can't use it either


def test_full_metadata_round_trips():
    recipe = Recipe(
        id="moussaka",
        name={"el": "Μουσακάς", "en": "Moussaka"},
        aliases={"el": [], "en": []},
        ingredients=["2 eggplants", "500 g minced beef"],
        steps=[RecipeStep(index=0, instruction={"en": "Fry the eggplant."}, section="Prep", suggested_duration_sec=600)],
        source=RecipeSource(site="example", source_id="42", url={"en": "https://example.com/m"},
                            imported_at="2026-09-25T00:00:00Z", author="A. Cook", fetched_at="2026-09-24T00:00:00Z"),
        language="en",
        servings="6",
        times=RecipeTimes(prep_min=30, cook_min=60, total_min=90),
        cuisine="Greek",
        nutrition={"calories": "450 kcal"},
        dietary={"vegetarian": False},
        ingredient_details=[
            IngredientLine(raw_text="2 eggplants", quantity="2", name="eggplants"),
            IngredientLine(raw_text="500 g minced beef", quantity="500", unit="g", name="minced beef", vocab_id="raw_meat"),
        ],
        equipment=[EquipmentItem(name="baking tray", vocab_id="baking_tray", inferred=True, text={"en": "baking tray", "el": "ταψί"})],
    )
    recipes.save_recipe(recipe, status=recipes.PUBLISHED, raw_source={"raw": True})
    assert recipes.get_recipe("moussaka").model_dump() == recipe.model_dump()
    assert recipes.source_payload("moussaka") == {"raw": True}


def test_edited_plain_ingredient_list_wins_over_stale_structure():
    recipe = Recipe(
        id="toast", name={"en": "Toast"}, aliases={}, ingredients=["bread", "butter"], steps=[],
        ingredient_details=[IngredientLine(raw_text="2 slices bread", quantity="2")],
    )
    recipes.save_recipe(recipe, status=recipes.PUBLISHED)
    assert recipes.get_recipe("toast").ingredients == ["bread", "butter"]


def test_database_itself_rejects_a_bad_id(fresh_db):
    recipes.ensure_ready()
    with pytest.raises(sqlite3.IntegrityError):
        with db.session(fresh_db) as conn:
            conn.execute("INSERT INTO recipes (id, name_json) VALUES ('../evil', '{}')")


def test_deleting_a_recipe_cascades_to_its_rows(fresh_db):
    recipes.delete_recipe("pasta")
    with db.session(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM steps WHERE recipe_id = 'pasta'").fetchone()[0] == 0


def test_detection_vocabulary_uses_linked_classes_and_follows_updates():
    first = recipes.detection_vocabulary("pancakes")
    assert {"pancake", "egg", "frying_pan", "hand"} <= first
    updated = recipes.get_recipe("pancakes").model_copy(update={"equipment": [EquipmentItem(name="whisk", vocab_id="whisk")]})
    recipes.save_recipe(updated, status=recipes.PUBLISHED)
    assert "whisk" in recipes.detection_vocabulary("pancakes")
    assert recipes.detection_vocabulary("no-such-recipe") is None


def test_bm25_search_is_accent_insensitive_and_serves_published_only():
    ids = lambda *words: [r.id for r in recipes.search_recipes(list(words))]  # noqa: E731
    # Greek ingredient lines are indexed too, so the pancakes' "2 αυγά" matches - after the egg dishes.
    assert ids("Αυγα") == ["scrambled_eggs", "greek_omelette", "pancakes"]
    assert "pasta" in ids("spaghetti")  # an alias
    assert ids("sushi") == []
    assert ids("σούσι") == []  # not "σου*" -> every "κουτ. σούπας"
    # Inflections: plural -> singular, both languages.
    assert ids("μπριζόλες")[0] == "beef_steak" and ids("σουβλάκια")[0] == "souvlaki" and ids("potatoes")[0] == "lemon_potatoes"
    # ...also where no alias spells the plural out (fold() makes a final "ς" a "σ").
    assert ids("σαλάτες") == ["greek_salad"] and ids("κοτόπουλα")[0] == "chicken_thighs_oven"
    assert {"tomato_pasta", "tomato_basil_soup"} <= set(ids("ντομάτες"))
    assert ids("μπριάμ") == ["briam"]  # not "μπρι*" -> μπριζόλα
    assert "briam" not in ids("eggs")  # a short stem matches exactly: "egg", never "egg*" -> eggplants
    assert set(ids("σούπα")) == {"lentil_soup", "tomato_basil_soup"}  # "κουτ. σούπας" is a tablespoon
    recipes.save_recipe(
        Recipe(id="s-omelette", name={"en": "Egg omelette"}, aliases={}, ingredients=["eggs"], steps=[]),
        status=recipes.STAGED,
    )
    assert "s-omelette" not in [r.id for r in recipes.search_recipes(["omelette", "eggs"])]


def test_search_index_follows_deletes_and_is_rebuilt_for_old_databases(fresh_db):
    recipes.delete_recipe("pasta")
    assert "pasta" not in [r.id for r in recipes.search_recipes(["pasta"])]
    with db.session(fresh_db) as conn:
        conn.execute("DELETE FROM recipe_search")  # simulate a database from before the index
    recipes._ready.clear()
    recipes.ensure_ready()
    assert [r.id for r in recipes.search_recipes(["pancakes"])] == ["pancakes"]


def test_seed_recipes_follow_the_curation_conventions():
    """What every hand-curated seed recipe needs for the hands-free flow (DESIGN #4, #23-#26):
    both languages everywhere the cook hears text, a kind on every step except a bare preheat,
    and raw protein flagged wherever meat, chicken or egg goes into the pan."""
    seed = [Recipe.model_validate(item) for item in json.loads(recipes.SEED_PATH.read_text(encoding="utf-8"))]
    assert len({r.id for r in seed}) == len(seed)
    for r in seed:
        assert r.source is None, f"{r.id}: seed recipes are hand-written, not imported"
        assert r.name.get("el") and r.name.get("en"), r.id
        assert r.equipment, f"{r.id}: the overview reads out the equipment"
        assert [d.raw_text for d in r.ingredient_details] == r.ingredients, r.id
        assert all(d.text.get("el") and d.text.get("en") for d in r.ingredient_details), r.id
        for s in r.steps:
            assert s.instruction.get("el") and s.instruction.get("en"), (r.id, s.index)
            assert bool(s.checkable) == bool(s.check_prompt_hint), (r.id, s.index)
            assert s.kind is not None or "preheat" in s.instruction["en"].lower(), (r.id, s.index)
        protein = {d.vocab_id for d in r.ingredient_details} & {"raw_meat", "chicken", "egg"}
        if protein and r.id != "pancakes":  # DESIGN #4: batter egg is curated as not-a-meat-check
            cooking = [s for s in r.steps if s.kind == "cook" and s.checkable]
            assert any(s.contains_raw_protein for s in cooking), f"{r.id}: no raw-protein cook step"


def test_reseed_drops_a_source_the_seed_no_longer_claims(fresh_db, tmp_path):
    recipes.ensure_ready()
    old = json.loads(recipes.SEED_PATH.read_text(encoding="utf-8"))[:1]
    old[0]["source"] = {"site": "open_source", "source_id": "x", "url": {"en": "https://example.org/pasta"},
                        "imported_at": "2026-09-25T00:00:00Z"}
    old_seed = tmp_path / "old.json"
    old_seed.write_text(json.dumps(old), encoding="utf-8")
    with db.session(fresh_db) as conn:
        recipes.seed_from_json(conn, old_seed)
    assert recipes.get_recipe(old[0]["id"]).source is not None
    with db.session(fresh_db) as conn:
        recipes.seed_from_json(conn)  # today's seed has no source for it
    assert recipes.get_recipe(old[0]["id"]).source is None
    assert recipes.find_source("https://example.org/pasta") is None


def test_equipment_is_read_out_in_the_cooks_language():
    beef = recipes.get_recipe("roast_beef")  # curated text survives the database round trip
    assert "θερμόμετρο κρέατος" in recipes.equipment_lines(beef, "el")
    assert "meat thermometer" in recipes.equipment_lines(beef, "en")
    bare = Recipe(id="eq-test", name={"en": "x"}, aliases={}, ingredients=[], steps=[],
                  equipment=[EquipmentItem(name="knife", vocab_id="knife"), EquipmentItem(name="skewers")])
    assert recipes.equipment_lines(bare, "el") == ["μαχαίρι", "skewers"]  # vocabulary label, else the name
    for r in recipes.all_recipes():
        assert len(recipes.equipment_lines(r, "el")) == len(r.equipment) > 0, r.id
