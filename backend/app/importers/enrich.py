"""Best-effort structure pulled out of free recipe text at import time. Pure functions.

Everything here is a *suggestion* for the human curator, never a decision: a parsed step
duration pre-fills the curation prompt, a matched ingredient links it to a detector class.
"""
from __future__ import annotations

import re
from typing import Optional

from app.detection.vocab_match import fold, match_classes
from app.detection.vocabulary import load_vocabulary

_NUM = r"(\d+(?:[.,]\d+)?|½|¼|¾)"
# Matched against folded text, so Greek words appear without accents ("έως" -> "εως", "ή" -> "η").
_RANGE_SEP = r"\s*(?:-|–|—|to|or|εως|η)\s*"
# Units after folding (casefolded, accents stripped). A number is required right before the
# unit, so the Greek "λεπτές φέτες" (thin slices) is never read as minutes.
_UNITS = {
    "hour": (r"hours?|hrs?|h\b|ωρες|ωρα|ωρων", 3600),
    "minute": (r"minutes?|mins?\b|min\b|λεπτα|λεπτο|λεπτων", 60),
    "second": (r"seconds?|secs?\b|δευτερολεπτα|δευτερολεπτο|δευτερολεπτων", 1),
}
_DURATION_RE = re.compile(
    rf"{_NUM}(?:{_RANGE_SEP}{_NUM})?\s*(?P<unit>{'|'.join(p for p, _ in _UNITS.values())})",
    re.IGNORECASE,
)
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}


def _number(token: str) -> float:
    return _FRACTIONS.get(token) or float(token.replace(",", "."))


def _unit_seconds(unit: str) -> int:
    for pattern, seconds in _UNITS.values():
        if re.fullmatch(pattern, unit, re.IGNORECASE):
            return seconds
    return 0


def duration_seconds(text: str) -> Optional[int]:
    """Total time a step's text mentions ("simmer 10-15 minutes, then rest 5 minutes" -> 1200 s).
    Ranges count at their upper end - better to check a little late than pull food early."""
    total = 0.0
    for m in _DURATION_RE.finditer(fold(text or "")):
        low, high = m.group(1), m.group(2)
        total += _number(high or low) * _unit_seconds(m.group("unit"))
    return int(round(total)) or None


_QTY_RE = re.compile(r"^\s*(?P<qty>(?:\d+\s+)?\d+(?:[.,/]\d+)?(?:\s*-\s*\d+(?:[.,/]\d+)?)?|½|¼|¾|⅓|⅔)\s*")
_UNIT_WORDS = sorted(
    [
        "g", "gr", "grams", "gram", "kg", "kilo", "kilos", "mg", "ml", "l", "litre", "litres", "liter", "liters",
        "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon", "teaspoons", "oz", "ounce",
        "ounces", "lb", "lbs", "pound", "pounds", "pinch", "clove", "cloves", "can", "cans", "slice", "slices",
        "γρ", "γρ.", "γραμμάρια", "κιλό", "κιλά", "ml.", "λίτρο", "λίτρα", "φλιτζάνι", "φλιτζάνια",
        "κ.σ.", "κ.γ.", "κουταλιά", "κουταλιές", "κουταλάκι", "κουταλάκια", "σκελίδα", "σκελίδες", "πρέζα",
    ],
    key=len,
    reverse=True,
)
_UNIT_RE = re.compile(r"^(?P<unit>" + "|".join(re.escape(u) for u in _UNIT_WORDS) + r")(?=\s|$)\s*", re.IGNORECASE)


def parse_ingredient_line(line: str) -> tuple[Optional[str], Optional[str], str]:
    """'2 tbsp olive oil' -> ('2', 'tbsp', 'olive oil'). Lines it can't split come back as the name."""
    rest = line.strip()
    qty = unit = None
    m = _QTY_RE.match(rest)
    if m:
        qty = m.group("qty").strip()
        rest = rest[m.end():]
        u = _UNIT_RE.match(rest)
        if u:
            unit = u.group("unit")
            rest = rest[u.end():]
    rest = re.sub(r"^(of|από)\s+", "", rest.strip(), flags=re.IGNORECASE)
    return qty, unit, rest or line.strip()


def ingredient_vocab_id(line: str) -> Optional[str]:
    """The detector class an ingredient line names, if any (first in vocabulary order)."""
    vocab = load_vocabulary()
    hits = match_classes([line])
    for cls in vocab.classes:
        if cls.id in hits and cls.group in ("ingredient", "food"):
            return cls.id
    return None


def equipment_vocab_id(name: str) -> Optional[str]:
    vocab = load_vocabulary()
    hits = match_classes([name])
    for cls in vocab.classes:
        if cls.id in hits and cls.group in ("utensil", "cookware", "appliance"):
            return cls.id
    return None


def infer_equipment(texts: list[str]) -> list[str]:
    """Tools/cookware/appliances the step text mentions, as vocabulary ids."""
    vocab = load_vocabulary()
    hits = match_classes(texts)
    return [c.id for c in vocab.classes if c.id in hits and c.group in ("utensil", "cookware", "appliance")]
