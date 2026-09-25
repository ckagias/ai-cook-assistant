from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Iterable

from app.importers.schema import StagedRecipe
from app.schemas import Recipe, RecipeSource, RecipeStep


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9\-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "recipe"


def _default_recipe_id(staged: StagedRecipe) -> str:
    title = staged.title.get("en") or staged.title.get("el") or "recipe"
    return _slugify(title)


def _prompt_yes_no(prompt: str, default_yes: bool, input_func: Callable[[str], str]) -> bool:
    suffix = "Y/n" if default_yes else "y/N"
    answer = input_func(f"{prompt} [{suffix}]: ").strip()
    if not answer:
        return default_yes
    return answer.lower().startswith("y")


def _parse_group_spec(raw: str) -> list[int]:
    spec = raw.strip()
    if not spec:
        return []
    values: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = [p.strip() for p in part.split("-", 1)]
            start = int(start_s)
            end = int(end_s)
            if end < start:
                start, end = end, start
            values.extend(range(start, end + 1))
        else:
            values.append(int(part))
    return values


def _ensure_grouping(staged: StagedRecipe, input_func: Callable[[str], str]) -> list[list[int]]:
    total = len(staged.steps)
    assigned: set[int] = set()
    groups: list[list[int]] = []
    while len(assigned) < total:
        remaining = [i for i in range(total) if i not in assigned]
        print("\nRemaining staged steps:")
        for i in remaining:
            step = staged.steps[i]
            section = step.section.get("en") or step.section.get("el") or ""
            text = step.text.get("en") or step.text.get("el") or ""
            print(f"  {i}: [{section}] {text}")

        raw = input_func("Enter the next step group as ranges (example: 0-2, 5): ").strip()
        group = _parse_group_spec(raw)
        if not group:
            print("No valid step indices were entered. Try again.")
            continue
        bad = [idx for idx in group if idx < 0 or idx >= total]
        if bad:
            print(f"Invalid step index(es): {bad}. Please use values between 0 and {total - 1}.")
            continue
        dupes = [idx for idx in set(group) if group.count(idx) > 1]
        if dupes:
            print(f"Duplicate step index(es) in the same group: {sorted(set(dupes))}")
            continue
        overlap = [idx for idx in group if idx in assigned]
        if overlap:
            print(f"These steps were already assigned: {overlap}. Please choose only remaining steps.")
            continue
        groups.append(group)
        assigned.update(group)

    return groups


def _default_ingredients(staged: StagedRecipe) -> list[str]:
    values: list[str] = []
    for ingredient in staged.ingredients:
        en = ingredient.title.get("en") or ingredient.title.get("el") or ""
        if en:
            values.append(en)
    return values


def _detect_raw_protein_hint(staged: StagedRecipe) -> str | None:
    haystack = " ".join(
        [
            *[ingredient.title.get("en", "") for ingredient in staged.ingredients],
            *[step.text.get("en", "") for step in staged.steps],
        ]
    ).lower()
    raw_terms = ["chicken", "beef", "pork", "fish", "egg", "eggs", "turkey", "lamb", "seafood", "shrimp"]
    hits = [term for term in raw_terms if term in haystack]
    if not hits:
        return None
    return "note: this recipe appears to include raw protein ingredients: " + ", ".join(hits)


def _collect_group_step(staged: StagedRecipe, group_indices: list[int], input_func: Callable[[str], str], group_number: int) -> RecipeStep:
    step_texts = [staged.steps[i].text.get("en") or staged.steps[i].text.get("el") or "" for i in group_indices]
    default_instruction = " ".join(step_texts).strip()
    en_instruction = input_func(f"Group {group_number} English instruction [{default_instruction}]: ").strip() or default_instruction
    el_instruction = input_func(f"Group {group_number} Greek instruction [{default_instruction}]: ").strip() or default_instruction

    is_checkable = _prompt_yes_no("Is this step checkable?", default_yes=False, input_func=input_func)
    expected_duration = None
    if is_checkable:
        raw = input_func("Expected duration in seconds [blank for none]: ").strip()
        expected_duration = int(raw) if raw else None
        check_prompt_hint = input_func("Check prompt hint [blank for none]: ").strip() or None
    else:
        check_prompt_hint = None

    raw_protein_default = False
    prompt = "Does this step contain raw protein?"
    raw_protein_msg = _detect_raw_protein_hint(staged)
    if raw_protein_msg:
        prompt = f"{prompt} - {raw_protein_msg}"
    raw_protein = _prompt_yes_no(prompt, default_yes=raw_protein_default, input_func=input_func)

    return RecipeStep(
        index=group_number,
        instruction={"el": el_instruction, "en": en_instruction},
        expected_duration_sec=expected_duration,
        checkable=is_checkable,
        check_prompt_hint=check_prompt_hint,
        contains_raw_protein=raw_protein,
    )


def run_curation(staged: StagedRecipe, input_func: Callable[[str], str] = input) -> Recipe:
    """Walk the curator through turning a staged recipe into the app schema."""
    print("\n=== Staged recipe preview ===")
    print(f"source: {staged.source}")
    print(f"source_id: {staged.source_id}")
    print(f"title: {staged.title}")
    print(f"category: {staged.category}")
    print(f"metadata: {staged.metadata.model_dump() if hasattr(staged.metadata, 'model_dump') else staged.metadata.dict()}")
    print("Ingredients:")
    for idx, ingredient in enumerate(staged.ingredients):
        title = ingredient.title.get("en") or ingredient.title.get("el") or ""
        print(f"  {idx}: {title} | qty={ingredient.quantity} | unit={ingredient.unit}")
    print("Steps:")
    for idx, step in enumerate(staged.steps):
        print(f"  {idx}: [{step.section.get('en') or step.section.get('el', '')}] {step.text.get('en') or step.text.get('el', '')}")

    suggested_id = _default_recipe_id(staged)
    recipe_id = input_func(f"Recipe id [{suggested_id}]: ").strip() or suggested_id

    ingredient_list = _default_ingredients(staged)
    if ingredient_list:
        printed = ", ".join(ingredient_list)
        accept = _prompt_yes_no(f"Accept ingredient list as-is: {printed} ?", default_yes=True, input_func=input_func)
        if not accept:
            raw = input_func("Enter the recipe ingredient list as comma-separated values: ").strip()
            ingredient_list = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        raw = input_func("No ingredients found; enter ingredients as comma-separated values: ").strip()
        ingredient_list = [item.strip() for item in raw.split(",") if item.strip()]

    groups = _ensure_grouping(staged, input_func)
    recipe_steps: list[RecipeStep] = []
    for group_index, group in enumerate(groups, start=0):
        recipe_steps.append(_collect_group_step(staged, group, input_func, group_index))

    recipe_name = {"el": staged.title.get("el", ""), "en": staged.title.get("en", "")}
    recipe = Recipe(
        id=recipe_id,
        name=recipe_name,
        aliases={"el": [], "en": []},
        ingredients=ingredient_list,
        steps=recipe_steps,
        source=RecipeSource(
            site=staged.source,
            source_id=staged.source_id,
            url=staged.source_url,
            imported_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    print("\nProposed Recipe:")
    print(recipe.model_dump_json(indent=2, ensure_ascii=False))
    confirm = _prompt_yes_no("Confirm this recipe?", default_yes=True, input_func=input_func)
    if not confirm:
        raise ValueError("Curation aborted by user")
    return recipe
