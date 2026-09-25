from __future__ import annotations

from app.curation.workflow import run_curation
from app.importers.schema import StagedMetadata, StagedRecipe, StagedStep, StagedIngredient


def _sample_staged():
    return StagedRecipe(
        source="akis_petretzikis",
        source_id="1001",
        source_url={"el": "https://example.com/el/1001", "en": "https://example.com/en/1001"},
        fetched_at="2026-01-01T00:00:00Z",
        title={"el": "Κοτόπουλο", "en": "Chicken"},
        category={"el": "Κυρίως", "en": "Main"},
        ingredients=[
            StagedIngredient(title={"el": "Κοτόπουλο", "en": "Chicken"}, quantity="500", unit={"el": "γρ", "en": "g"}),
            StagedIngredient(title={"el": "Σκόρδο", "en": "Garlic"}, quantity="2", unit={"el": "σκελίδες", "en": "cloves"}),
        ],
        steps=[
            StagedStep(section={"el": "Ετοιμασία", "en": "Prep"}, text={"el": "Κόψε το κοτόπουλο.", "en": "Cut the chicken."}),
            StagedStep(section={"el": "Μαγείρεμα", "en": "Cook"}, text={"el": "Τηγάνισε το.", "en": "Fry it."}),
        ],
        metadata=StagedMetadata(
            make_time_min=20,
            servings="2",
            difficulty="easy",
            dietary_flags={},
            equipment=["pan"],
            image_url=None,
            video_url=None,
        ),
    )


def make_input_factory(answers):
    answers = list(answers)

    def _input(prompt):
        if not answers:
            raise AssertionError(f"No answer left for prompt: {prompt!r}")
        return answers.pop(0)

    return _input


def test_run_curation_happy_path():
    staged = _sample_staged()
    prompts = [
        "",  # recipe id default
        "y",  # accept ingredient list as-is
        "0-1",  # group both steps
        "",  # English instruction default
        "",  # Greek instruction default
        "n",  # not checkable
        "n",  # raw protein? no
        "y",  # confirm recipe
    ]
    recipe = run_curation(staged, input_func=make_input_factory(prompts))
    assert recipe.id == "chicken"
    assert recipe.ingredients == ["Chicken", "Garlic"]
    assert len(recipe.steps) == 1
    assert recipe.steps[0].index == 0
    assert recipe.steps[0].contains_raw_protein is False
    assert recipe.source is not None
    assert recipe.source.site == "akis_petretzikis"


def test_run_curation_rejects_incomplete_step_grouping():
    staged = _sample_staged()
    prompts = [
        "",  # recipe id
        "y",  # accept ingredients
        "0",  # only assign first step, leave one ungrouped
        "",  # English
        "",  # Greek
        "n",  # not checkable
        "n",  # raw protein
        "0-1",  # avoid infinite loop by finishing assignment, though this path isn't reached because earlier step assignment is not validated as complete? It will continue as we expect.
    ]
    # This flow intentionally keeps some steps un-assigned; the workflow should ask again until complete.
    queue = [
        "", "y", "0", "", "", "n", "n",
        "1", "", "", "n", "n",
        "y",
    ]
    recipe = run_curation(staged, input_func=make_input_factory(queue))
    assert len(recipe.steps) == 2


def test_run_curation_requires_explicit_raw_protein_flag():
    staged = _sample_staged()
    prompts = [
        "", "y", "0-1", "", "", "n", "y", "y",
    ]
    recipe = run_curation(staged, input_func=make_input_factory(prompts))
    assert recipe.steps[0].contains_raw_protein is True
