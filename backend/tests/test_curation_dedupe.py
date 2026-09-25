from app.curation.dedupe import find_possible_duplicates
from app.schemas import Recipe, RecipeStep


def _make_recipe(recipe_id: str, en_name: str, el_name: str, aliases=None):
    aliases = aliases or {"en": [], "el": []}
    return Recipe(
        id=recipe_id,
        name={"en": en_name, "el": el_name},
        aliases=aliases,
        ingredients=["x"],
        steps=[
            RecipeStep(
                index=0,
                instruction={"en": "Do this", "el": "Κάνε αυτό"},
                expected_duration_sec=None,
                checkable=False,
                check_prompt_hint=None,
                reference_image=None,
                contains_raw_protein=False,
            )
        ],
    )


def test_find_possible_duplicates_exact_title_match():
    existing = [_make_recipe("p1", "Chicken Soup", "Κοτόπουλο Σούπα")]
    matches = find_possible_duplicates({"en": "Chicken Soup", "el": "Κοτόπουλο Σούπα"}, existing)
    assert matches == existing


def test_find_possible_duplicates_token_overlap():
    existing = [_make_recipe("p2", "Tomato Pasta", "Ντομάτα Μακαρόνια")]
    matches = find_possible_duplicates({"en": "Pasta with Tomato", "el": "Μακαρόνια με ντομάτα"}, existing)
    assert matches == existing


def test_find_possible_duplicates_unrelated_recipe_is_not_flagged():
    existing = [_make_recipe("p3", "Salad", "Σαλάτα")]
    matches = find_possible_duplicates({"en": "Chicken Curry", "el": "Κοτόπουλο Κάρυ"}, existing)
    assert matches == []
