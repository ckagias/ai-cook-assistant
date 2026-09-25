from __future__ import annotations

import re
from collections.abc import Iterable

from app.schemas import Recipe


def _normalize_text(value: str) -> str:
    value = value.casefold()
    value = value.replace("ά", "α").replace("έ", "ε").replace("ή", "η").replace("ί", "ι").replace("ό", "ο").replace("ύ", "υ").replace("ώ", "ω").replace("ϊ", "ι").replace("ΐ", "ι").replace("ϋ", "υ").replace("ΰ", "υ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokenize(value: str) -> set[str]:
    return {tok for tok in re.split(r"\s+", _normalize_text(value)) if tok}


def find_possible_duplicates(candidate_title: dict[str, str], existing: list[Recipe]) -> list[Recipe]:
    """Return existing recipes that are likely duplicates of the new candidate title."""
    candidate_values = {
        "en": [candidate_title.get("en", "")],
        "el": [candidate_title.get("el", "")],
    }

    matches: list[Recipe] = []
    for recipe in existing:
        all_names_by_lang = {
            "en": [recipe.name.get("en", ""), *recipe.aliases.get("en", [])],
            "el": [recipe.name.get("el", ""), *recipe.aliases.get("el", [])],
        }

        for lang in ("en", "el"):
            candidate_names = [value for value in candidate_values[lang] if value]
            if not candidate_names:
                continue

            for recipe_name in all_names_by_lang[lang]:
                if not recipe_name:
                    continue

                norm_candidate = [_normalize_text(value) for value in candidate_names]
                norm_recipe = _normalize_text(recipe_name)
                if norm_recipe in norm_candidate:
                    matches.append(recipe)
                    break

                candidate_tokens = set().union(*(_tokenize(value) for value in norm_candidate))
                recipe_tokens = _tokenize(norm_recipe)
                if candidate_tokens and recipe_tokens:
                    overlap = len(candidate_tokens & recipe_tokens)
                    union = len(candidate_tokens | recipe_tokens)
                    if union and (overlap / union) >= 0.5:
                        matches.append(recipe)
                        break
            if recipe in matches:
                break
    return matches
