"""Find vocabulary classes mentioned in free recipe text (English or Greek).

Used to narrow /detect to one recipe's ingredients and equipment, and by the recipe importer
to link ingredients/equipment to detector classes. Keyword matching, not NLP: accents and
case are folded, and a synonym may carry up to two trailing letters so plurals and Greek
case endings still match ("egg" -> "eggs", "κατσαρόλα" -> "κατσαρόλας") while "pan" does
not match "pancake".
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Iterable

from .vocabulary import Vocabulary, load_vocabulary

_MAX_SUFFIX = 2


def fold(text: str) -> str:
    """Casefold and strip accents/diacritics (Greek tonos and dialytika included)."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


@lru_cache(maxsize=4)
def _patterns(vocab_fingerprint: str) -> list[tuple[str, re.Pattern]]:
    vocab = load_vocabulary()
    compiled = []
    for cls in vocab.classes:
        terms = {cls.en, cls.el, *(t for ts in cls.synonyms.values() for t in ts)}
        alternatives = sorted({re.escape(fold(t)) for t in terms if t.strip()}, key=len, reverse=True)
        pattern = re.compile(r"(?<!\w)(?:" + "|".join(alternatives) + r")\w{0," + str(_MAX_SUFFIX) + r"}(?!\w)")
        compiled.append((cls.id, pattern))
    return compiled


def match_classes(texts: Iterable[str], vocab: Vocabulary | None = None) -> set[str]:
    vocab = vocab or load_vocabulary()
    haystack = " \n ".join(fold(t) for t in texts if t)
    if not haystack:
        return set()
    return {class_id for class_id, pattern in _patterns(vocab.fingerprint()) if pattern.search(haystack)}
