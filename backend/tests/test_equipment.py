"""Equipment before step 1: the seed data, bilingual names through the database, and the
voice model seeing it."""
import json

import pytest

from app import recipes, voice
from app.detection.vocabulary import load_vocabulary
from app.schemas import EquipmentItem, Recipe

GEAR = ("utensil", "cookware", "appliance")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "cook.db"))


def test_every_seed_recipe_lists_bilingual_equipment_linked_to_the_detector():
    vocab = load_vocabulary()
    for item in json.loads(recipes.SEED_PATH.read_text(encoding="utf-8")):
        recipe = Recipe.model_validate(item)
        assert recipe.equipment, recipe.id
        names = [e.name for e in recipe.equipment]
        assert len(names) == len(set(names)), recipe.id  # (recipe_id, name) is the primary key
        for e in recipe.equipment:
            assert set(e.text) == {"en", "el"} and e.text["en"] == e.name, (recipe.id, e.name)
            if e.vocab_id is not None:
                cls = vocab.by_id(e.vocab_id)
                assert cls is not None and cls.group in GEAR, (recipe.id, e.vocab_id)


def test_equipment_round_trips_and_reads_in_the_cooks_language():
    recipe = recipes.get_recipe("roast_beef")
    assert recipes.equipment_lines(recipe, "el") == [
        "επιφάνεια κοπής", "μαχαίρι", "ταψί", "φούρνος", "θερμόμετρο κρέατος", "αλουμινόχαρτο"]
    assert recipes.equipment_lines(recipe, "en")[:3] == ["cutting board", "knife", "baking tray"]
    assert "baking_tray" in recipes.detection_vocabulary("roast_beef")  # so the camera can tick it


def test_equipment_without_a_translation_borrows_the_vocabulary_word():
    recipes.save_recipe(Recipe(
        id="fry", name={"en": "Fry"}, aliases={}, ingredients=[], steps=[], language="en",
        equipment=[EquipmentItem(name="frying pan", vocab_id="frying_pan"), EquipmentItem(name="apron")],
    ), status=recipes.PUBLISHED)
    recipes.save_recipe(Recipe(
        id="tigani", name={"el": "Τηγάνι"}, aliases={}, ingredients=[], steps=[], language="el",
        equipment=[EquipmentItem(name="Τηγάνι", vocab_id="frying_pan")],
    ), status=recipes.PUBLISHED)
    # Marked Greek, written in English (feature/detection-db's seed recipes look like this).
    recipes.save_recipe(Recipe(
        id="souvlaki-en", name={"el": "Σουβλάκια"}, aliases={}, ingredients=[], steps=[], language="el",
        equipment=[EquipmentItem(name="tongs", vocab_id="tongs")],
    ), status=recipes.PUBLISHED)
    fry = recipes.get_recipe("fry")
    assert recipes.equipment_lines(fry, "el") == ["τηγάνι", "apron"]
    assert recipes.equipment_lines(fry, "en") == ["frying pan", "apron"]
    assert recipes.equipment_lines(recipes.get_recipe("tigani"), "en") == ["frying pan"]
    assert recipes.equipment_lines(recipes.get_recipe("souvlaki-en"), "el") == ["λαβίδα"]


def test_the_voice_model_knows_the_equipment():
    text = voice.build_user_text("do I need a blender?", "en", "pasta", None, [])
    assert "Equipment: large pot; colander; stove" in text
