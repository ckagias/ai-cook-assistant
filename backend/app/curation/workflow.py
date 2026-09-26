from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Optional

from app.curation.dedupe import find_possible_duplicates
from app.importers.schema import StagedRecipe
from app.schemas import Recipe, RecipeSource, RecipeStep

# Vocabulary classes that mean "raw protein might be in this step" - a nudge for the curator,
# never a default. The pancake batter (raw egg, curated False) is why a human decides.
RAW_PROTEIN_CLASSES = {"egg", "chicken", "raw_meat", "seafood"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9\-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:64].strip("-") or "recipe"


def _default_recipe_id(staged: StagedRecipe) -> str:
    title = staged.title.get("en") or staged.title.get("el") or "recipe"
    return _slugify(title)


def _default_id_taken(recipe_id: str) -> bool:
    from app import recipes as recipes_module

    return recipes_module.get_recipe(recipe_id, status=None) is not None


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


def _choose_recipe_id(suggested: str, input_func, id_taken: Callable[[str], bool], replaces: Optional[str]) -> str:
    """Ask for an id until it is valid and not already another recipe's - a new recipe must
    never silently overwrite a curated one (merge replaces by id)."""
    while True:
        candidate = input_func(f"Recipe id [{suggested}]: ").strip() or suggested
        if not ID_PATTERN.match(candidate):
            print("Ids are 1-64 chars: lowercase letters, digits, '-' and '_', starting with a letter or digit.")
            suggested = _slugify(candidate)
            continue
        if candidate != replaces and id_taken(candidate):
            n = 2
            while id_taken(f"{candidate}-{n}"):
                n += 1
            print(f"'{candidate}' is already a recipe id. Choose another (or use the duplicate prompt to update it).")
            suggested = f"{candidate}-{n}"
            continue
        return candidate


def _ensure_grouping(staged: StagedRecipe, input_func: Callable[[str], str]) -> list[RecipeStep]:
    total = len(staged.steps)
    assigned: set[int] = set()
    recipe_steps: list[RecipeStep] = []
    while len(assigned) < total:
        remaining = [i for i in range(total) if i not in assigned]
        print("\nRemaining staged steps:")
        for i in remaining:
            step = staged.steps[i]
            section = step.section.get("en") or step.section.get("el") or ""
            text = step.text.get("en") or step.text.get("el") or ""
            print(f"  {i}: [{section}] {text}")

        raw = input_func("Enter the next step group as ranges (example: 0-2, 5): ").strip()
        if not raw:
            print("No valid step indices were entered. Try again.")
            continue
        try:
            group = _parse_group_spec(raw)
        except ValueError:
            print("Invalid range format. Use numbers or ranges like 0-2, 5.")
            continue
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
        assigned.update(group)
        recipe_steps.append(_collect_group_step(staged, group, input_func, len(recipe_steps)))

    return recipe_steps


def _default_ingredients(staged: StagedRecipe) -> list[str]:
    values: list[str] = []
    for ingredient in staged.ingredients:
        en = ingredient.title.get("en") or ingredient.title.get("el") or ""
        if en:
            values.append(en)
    return values


def _raw_protein_hint(staged: StagedRecipe, group_indices: list[int]) -> Optional[str]:
    from app.detection.vocab_match import match_classes

    group_texts = [t for i in group_indices for t in staged.steps[i].text.values()]
    hits = match_classes(group_texts) & RAW_PROTEIN_CLASSES
    if hits:
        return "note: this step's text mentions " + ", ".join(sorted(hits))
    recipe_texts = [t for ing in staged.ingredients for t in ing.title.values()]
    hits = match_classes(recipe_texts) & RAW_PROTEIN_CLASSES
    if hits:
        return "note: the recipe's ingredients include " + ", ".join(sorted(hits))
    return None


def _ask_duration(default: Optional[int], input_func) -> Optional[int]:
    shown = str(default) if default else "none"
    while True:
        raw = input_func(f"Expected duration in seconds (starts a timer) [{shown}; '-' for none]: ").strip()
        if not raw:
            return default
        if raw == "-":
            return None
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number of seconds, blank for the default, or '-' for none.")
            continue
        return value if value > 0 else None


def _collect_group_step(staged: StagedRecipe, group_indices: list[int], input_func: Callable[[str], str], group_number: int) -> RecipeStep:
    def joined(lang: str) -> str:
        return " ".join(staged.steps[i].text.get(lang) or "" for i in group_indices).strip()

    en_default = joined("en") or joined("el")
    # The Greek default must be the Greek text - an English sentence read by the Greek voice is useless.
    el_default = joined("el") or joined("en")
    en_instruction = input_func(f"Group {group_number} English instruction [{en_default}]: ").strip() or en_default
    el_instruction = input_func(f"Group {group_number} Greek instruction [{el_default}]: ").strip() or el_default

    is_checkable = _prompt_yes_no("Is this step checkable?", default_yes=False, input_func=input_func)
    check_prompt_hint = None
    if is_checkable:
        check_prompt_hint = input_func("Check prompt hint [blank for none]: ").strip() or None

    suggestions = [staged.steps[i].suggested_duration_sec for i in group_indices if staged.steps[i].suggested_duration_sec]
    expected_duration = _ask_duration(sum(suggestions) if suggestions else None, input_func)

    prompt = "Does this step contain raw protein?"
    hint = _raw_protein_hint(staged, group_indices)
    if hint:
        prompt = f"{prompt} - {hint}"
    raw_protein = _prompt_yes_no(prompt, default_yes=False, input_func=input_func)

    return RecipeStep(
        index=group_number,
        instruction={"el": el_instruction, "en": en_instruction},
        expected_duration_sec=expected_duration,
        checkable=is_checkable,
        check_prompt_hint=check_prompt_hint,
        contains_raw_protein=raw_protein,
    )


def run_curation(
    staged: StagedRecipe,
    input_func: Callable[[str], str] = input,
    *,
    id_taken: Optional[Callable[[str], bool]] = None,
    replaces: Optional[str] = None,
    base: Optional[Recipe] = None,
    existing: Optional[list[Recipe]] = None,
) -> Recipe:
    """Walk the curator through turning a staged recipe into the app schema.

    replaces: id of the staged database record being curated (it may keep its own id).
    base:     that staged record - its metadata (times, servings, nutrition, structured
              ingredients, equipment) carries over to the published recipe.
    """
    id_taken = id_taken or _default_id_taken
    print("\n=== Staged recipe preview ===")
    print(f"source: {staged.source}")
    print(f"source_id: {staged.source_id}")
    print(f"title: {staged.title}")
    print(f"category: {staged.category}")
    print(f"metadata: {staged.metadata.model_dump()}")
    print("Ingredients:")
    for idx, ingredient in enumerate(staged.ingredients):
        title = ingredient.title.get("en") or ingredient.title.get("el") or ""
        print(f"  {idx}: {title} | qty={ingredient.quantity} | unit={ingredient.unit}")
    print("Steps:")
    for idx, step in enumerate(staged.steps):
        print(f"  {idx}: [{step.section.get('en') or step.section.get('el', '')}] {step.text.get('en') or step.text.get('el', '')}")

    recipe_id = _choose_recipe_id(_default_recipe_id(staged), input_func, id_taken, replaces)

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

    recipe_steps = _ensure_grouping(staged, input_func)

    recipe_name = {"el": staged.title.get("el", ""), "en": staged.title.get("en", "")}
    aliases: dict[str, list[str]] = {"el": [], "en": []}

    # Human review for duplicate candidates before final confirmation.
    if existing is None:
        try:
            from app import recipes as recipes_module

            existing = recipes_module.all_recipes()
        except Exception:
            existing = []
    duplicates = find_possible_duplicates(recipe_name, existing)
    if duplicates:
        print("\nPossible duplicates found:")
        for dup in duplicates:
            print(f"  - {dup.id}: {dup.name}")
        choice = input_func("Choose: [n]ew recipe, [u]pdate existing, [a]bort: ").strip().lower()
        if choice == "u":
            target = duplicates[0]
            recipe_id = target.id
            # Updating replaces steps/ingredients; the curated identity (name, aliases) and any
            # reference photos already installed for a step index are kept.
            recipe_name = dict(target.name)
            aliases = {lang: list(values) for lang, values in target.aliases.items()}
            for lang, title in staged.title.items():
                if title and title not in aliases.setdefault(lang, []) and title != recipe_name.get(lang):
                    aliases[lang].append(title)
            old_refs = {s.index: s.reference_image for s in target.steps if s.reference_image}
            recipe_steps = [s.model_copy(update={"reference_image": old_refs.get(s.index)}) for s in recipe_steps]
        elif choice == "a":
            raise ValueError("Duplicate review aborted by user")

    recipe = Recipe(
        id=recipe_id,
        name=recipe_name,
        aliases=aliases,
        ingredients=ingredient_list,
        steps=recipe_steps,
        source=RecipeSource(
            site=staged.source,
            source_id=staged.source_id,
            url=staged.source_url,
            imported_at=datetime.now(timezone.utc).isoformat(),
            fetched_at=staged.fetched_at,
        ),
    )
    if base is not None:
        recipe = recipe.model_copy(update={
            "description": base.description, "language": base.language, "servings": base.servings,
            "times": base.times, "difficulty": base.difficulty, "cuisine": base.cuisine, "category": base.category,
            "image_url": base.image_url, "video_url": base.video_url, "nutrition": base.nutrition,
            "dietary": base.dietary, "ingredient_details": base.ingredient_details, "equipment": base.equipment,
            "source": recipe.source.model_copy(update={"author": base.source.author if base.source else None}),
        })

    print("\nProposed Recipe:")
    print(recipe.model_dump_json(indent=2, ensure_ascii=False))
    for step in recipe.steps:
        if step.checkable and not step.reference_image:
            print(f"  reminder: step {step.index} is checkable - consider scripts/add_reference.py for a reference photo")
    confirm = _prompt_yes_no("Confirm this recipe?", default_yes=True, input_func=input_func)
    if not confirm:
        raise ValueError("Curation aborted by user")
    return recipe
