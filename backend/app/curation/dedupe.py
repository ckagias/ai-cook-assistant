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
    candidate_values = [candidate_title.get("en", ""), candidate_title.get("el", "")]
    normalized = [_normalize_text(v) for v in candidate_values if v]

    matches: list[Recipe] = []
    for recipe in existing:
        names = [recipe.name.get("en", ""), recipe.name.get("el", "")]
        aliases = [item for group in recipe.aliases.values() for item in group]
        all_names = [*names, *aliases]
        for name in all_names:
            if not name:
                continue
            norm_name = _normalize_text(name)
            if norm_name in normalized:
                matches.append(recipe)
                break

            tokens_candidate = set().union(*(_tokenize(v) for v in normalized)) if normalized else set()
            tokens_recipe = _tokenize(norm_name)
            if tokens_candidate and tokens_recipe:
                overlap = len(tokens_candidate & tokens_recipe)
                union = len(tokens_candidate | tokens_recipe)
                if union and (overlap / union) >= 0.5:
                    matches.append(recipe)
                    break
    return matches
