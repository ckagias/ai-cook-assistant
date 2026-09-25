import json

import pytest

from app.curation import staged as staged_module
from app.importers.schema import StagedRecipe


@pytest.fixture
def staged_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(staged_module, "STAGING_ROOT", tmp_path / "staging")
    source_dir = tmp_path / "staging" / "akis_petretzikis"
    source_dir.mkdir(parents=True)

    good_a = {
        "source": "akis_petretzikis",
        "source_id": "1001",
        "source_url": {"el": "https://example.com/el/1001", "en": "https://example.com/en/1001"},
        "fetched_at": "2026-01-01T00:00:00Z",
        "title": {"el": "Κοτόπουλο", "en": "Chicken"},
        "category": {"el": "Κυρίως", "en": "Main"},
        "ingredients": [
            {"title": {"el": "Κοτόπουλο", "en": "Chicken"}, "quantity": "500", "unit": {"el": "γρ", "en": "g"}, "info": {"el": "", "en": ""}}
        ],
        "steps": [{"section": {"el": "Ετοιμασία", "en": "Preparation"}, "text": {"el": "Κόψε το κρέας.", "en": "Cut the meat."}}],
        "metadata": {
            "make_time_min": 30,
            "bake_time_min": None,
            "servings": "2",
            "difficulty": "easy",
            "dietary_flags": {"vegetarian": False},
            "equipment": ["pan"],
            "image_url": None,
            "video_url": None,
        },
    }
    good_b = {
        "source": "akis_petretzikis",
        "source_id": "1002",
        "source_url": {"el": "https://example.com/el/1002", "en": "https://example.com/en/1002"},
        "fetched_at": "2026-01-01T00:00:00Z",
        "title": {"el": "Τηγανιτές", "en": "Pancakes"},
        "category": {"el": "Γλυκά", "en": "Desserts"},
        "ingredients": [],
        "steps": [{"section": {"el": "Μαγειρική", "en": "Cooking"}, "text": {"el": "Ανακάτεψε.", "en": "Mix."}}],
        "metadata": {
            "make_time_min": 15,
            "bake_time_min": None,
            "servings": "4",
            "difficulty": "easy",
            "dietary_flags": {},
            "equipment": [],
            "image_url": None,
            "video_url": None,
        },
    }

    (source_dir / "1001.json").write_text(json.dumps(good_a, ensure_ascii=False), encoding="utf-8")
    (source_dir / "1002.json").write_text(json.dumps(good_b, ensure_ascii=False), encoding="utf-8")
    (source_dir / "manifest.json").write_text(json.dumps({"count": 2}), encoding="utf-8")

    return source_dir


def test_list_staged_returns_valid_recipes_only(staged_tree):
    recipes = staged_module.list_staged("akis_petretzikis")
    assert [r.source_id for r in recipes] == ["1001", "1002"]
    assert all(isinstance(r, StagedRecipe) for r in recipes)


def test_list_staged_filters_by_source(staged_tree):
    other_dir = staged_tree.parent / "other_site"
    other_dir.mkdir()
    payload = {
        "source": "other_site",
        "source_id": "2001",
        "source_url": {"el": "https://example.com/el/2001", "en": "https://example.com/en/2001"},
        "fetched_at": "2026-01-01T00:00:00Z",
        "title": {"el": "Κέικ", "en": "Cake"},
        "category": {"el": "Γλυκά", "en": "Desserts"},
        "ingredients": [],
        "steps": [],
        "metadata": {"dietary_flags": {}, "equipment": [], "image_url": None, "video_url": None},
    }
    (other_dir / "2001.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    all_recipes = staged_module.list_staged()
    assert {r.source for r in all_recipes} == {"akis_petretzikis", "other_site"}
    assert [r.source_id for r in staged_module.list_staged("other_site")] == ["2001"]


def test_get_staged_finds_and_missing_returns_none(staged_tree):
    assert staged_module.get_staged("akis_petretzikis", "1001").source_id == "1001"
    assert staged_module.get_staged("akis_petretzikis", "missing") is None


def test_invalid_staged_file_raises_clear_error(staged_tree):
    broken = staged_tree / "broken.json"
    broken.write_text("{not valid json}", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.json"):
        staged_module.list_staged("akis_petretzikis")
