from __future__ import annotations

import pytest

from app.curation.workflow import run_curation
from app.importers.schema import StagedIngredient, StagedMetadata, StagedRecipe, StagedStep
from app.schemas import Recipe, RecipeStep


def _sample_staged(title_en="Chicken", title_el="Κοτόπουλο", durations=(None, None)):
    return StagedRecipe(
        source="akis_petretzikis",
        source_id="1001",
        source_url={"el": "https://example.com/el/1001", "en": "https://example.com/en/1001"},
        fetched_at="2026-01-01T00:00:00Z",
        title={"el": title_el, "en": title_en},
        category={"el": "Κυρίως", "en": "Main"},
        ingredients=[
            StagedIngredient(title={"el": "Κοτόπουλο", "en": "Chicken"}, quantity="500", unit={"el": "γρ", "en": "g"}),
            StagedIngredient(title={"el": "Σκόρδο", "en": "Garlic"}, quantity="2", unit={"el": "σκελίδες", "en": "cloves"}),
        ],
        steps=[
            StagedStep(section={"el": "Ετοιμασία", "en": "Prep"}, text={"el": "Κόψε το κοτόπουλο.", "en": "Cut the chicken."},
                       suggested_duration_sec=durations[0]),
            StagedStep(section={"el": "Μαγείρεμα", "en": "Cook"}, text={"el": "Τηγάνισε το.", "en": "Fry it."},
                       suggested_duration_sec=durations[1]),
        ],
        metadata=StagedMetadata(make_time_min=20, servings="2", difficulty="easy", equipment=["pan"]),
    )


def make_input_factory(answers):
    answers = list(answers)
    prompts = []

    def _input(prompt):
        prompts.append(prompt)
        if not answers:
            raise AssertionError(f"No answer left for prompt: {prompt!r}")
        return answers.pop(0)

    _input.prompts = prompts
    return _input


def curate(staged, answers, **kwargs):
    kwargs.setdefault("id_taken", lambda _id: False)
    kwargs.setdefault("existing", [])
    return run_curation(staged, input_func=make_input_factory(answers), **kwargs)


# Per step group: English, Greek, checkable?, [hint if checkable], duration, raw protein?
ONE_GROUP = ["", "y", "0-1", "", "", "n", "", "n", "y"]


def test_run_curation_happy_path():
    recipe = curate(_sample_staged(), ONE_GROUP)
    assert recipe.id == "chicken"
    assert recipe.ingredients == ["Chicken", "Garlic"]
    assert len(recipe.steps) == 1
    assert recipe.steps[0].index == 0
    assert recipe.steps[0].contains_raw_protein is False
    assert recipe.source is not None
    assert recipe.source.site == "akis_petretzikis"


def test_greek_instruction_defaults_to_the_greek_text():
    recipe = curate(_sample_staged(), ONE_GROUP)
    assert recipe.steps[0].instruction["el"] == "Κόψε το κοτόπουλο. Τηγάνισε το."
    assert recipe.steps[0].instruction["en"] == "Cut the chicken. Fry it."


def test_run_curation_keeps_asking_until_every_step_is_grouped():
    queue = [
        "", "y",
        "0", "", "", "n", "", "n",
        "1", "", "", "n", "", "n",
        "y",
    ]
    recipe = curate(_sample_staged(), queue)
    assert len(recipe.steps) == 2


def test_run_curation_requires_explicit_raw_protein_flag():
    recipe = curate(_sample_staged(), ["", "y", "0-1", "", "", "n", "", "y", "y"])
    assert recipe.steps[0].contains_raw_protein is True


def test_raw_protein_prompt_names_what_the_step_mentions():
    ask = make_input_factory(ONE_GROUP)
    run_curation(_sample_staged(), input_func=ask, id_taken=lambda _: False, existing=[])
    protein_prompt = next(p for p in ask.prompts if "raw protein" in p)
    assert "chicken" in protein_prompt


def test_duration_is_asked_for_every_step_and_prefilled_from_the_importer():
    # Not checkable, yet a timer duration is still collected - the suggestions are summed.
    recipe = curate(_sample_staged(durations=(60, 600)), ONE_GROUP)
    assert recipe.steps[0].checkable is False
    assert recipe.steps[0].expected_duration_sec == 660


def test_duration_can_be_cleared_or_overridden():
    cleared = curate(_sample_staged(durations=(60, None)), ["", "y", "0-1", "", "", "n", "-", "n", "y"])
    assert cleared.steps[0].expected_duration_sec is None
    typed = curate(_sample_staged(), ["", "y", "0-1", "", "", "y", "Golden?", "300", "n", "y"])
    assert typed.steps[0].expected_duration_sec == 300
    assert typed.steps[0].check_prompt_hint == "Golden?"


def test_colliding_id_is_refused_and_an_alternative_suggested():
    taken = {"chicken"}
    ask = make_input_factory(["", ""] + ONE_GROUP[1:])  # accept the default twice
    recipe = run_curation(_sample_staged(), input_func=ask, id_taken=lambda i: i in taken, existing=[])
    assert recipe.id == "chicken-2"


def test_invalid_id_is_refused():
    recipe = curate(_sample_staged(), ["Bad Id!", "bad-id"] + ONE_GROUP[1:])
    assert recipe.id == "bad-id"


def test_curating_a_staged_record_may_keep_its_own_id():
    # The staged record itself is "taken", but it's the one being replaced.
    recipe = curate(_sample_staged(), ["s-abc123"] + ONE_GROUP[1:], id_taken=lambda _: True, replaces="s-abc123")
    assert recipe.id == "s-abc123"


def test_update_existing_keeps_name_aliases_and_reference_photos():
    existing = Recipe(
        id="chicken",
        name={"en": "Chicken", "el": "Κοτόπουλο"},
        aliases={"en": ["roast chicken"], "el": []},
        ingredients=["chicken"],
        steps=[RecipeStep(index=0, instruction={"en": "x", "el": "x"}, reference_image="chicken_done.jpg")],
    )
    staged = _sample_staged(title_en="Lemon Chicken", title_el="Κοτόπουλο λεμονάτο")
    answers = ["lemon-chicken", "y", "0-1", "", "", "n", "", "n", "u", "y"]
    recipe = curate(staged, answers, existing=[existing])
    assert recipe.id == "chicken"
    assert recipe.name == existing.name
    assert "roast chicken" in recipe.aliases["en"] and "Lemon Chicken" in recipe.aliases["en"]
    assert recipe.steps[0].reference_image == "chicken_done.jpg"


def test_abort_on_duplicate():
    existing = Recipe(id="chicken", name={"en": "Chicken", "el": "Κοτόπουλο"}, aliases={}, ingredients=[], steps=[])
    with pytest.raises(ValueError, match="aborted"):
        curate(_sample_staged(), ["", "y", "0-1", "", "", "n", "", "n", "a"], existing=[existing])
