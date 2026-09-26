import logging
import re
import unicodedata

from . import vision

logger = logging.getLogger(__name__)


def fold(text: str) -> str:
    """Casefold and strip accents, so Greek markers match with or without tonos."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# Patterns that suggest the model is reporting on/responding to injected instructions rather
# than describing the photo. Matched against accent-folded, casefolded text. Short, reviewed,
# and expected to grow - not a claim of completeness. Phrased tightly on purpose: a bare
# "you are now" would also catch the perfectly normal "you are now ready to flip".
# Patterns go through the same fold() as the text (casefold also turns the final sigma ς
# into σ), so both sides are always normalized identically.
_MARKER_PATTERNS = tuple(
    re.compile(fold(p))
    for p in (
        # English
        r"ignore (all |the |any )?(previous|prior|above|earlier)",
        r"\bas an ai\b",
        r"\b(i am|i'm|you are|you're) now (a|an)\b",
        r"system prompt",
        r"new instructions",
        # Greek (folded: no accents)
        r"(προηγουμεν\w*|παραπανω) οδηγι\w*",
        r"\bνε(ες|α|ων) οδηγι\w*",
        r"\b(ειμαι|εισαι) (πλεον|τωρα) (ενας|μια|ενα)\b",
        r"(μηνυμα|οδηγιες|προτροπη) (του )?συστηματος",
        r"\bως (τεχνητη νοημοσυνη|μοντελο)\b",
    )
)

# A cooking answer never needs to read out a web address - its only use would be to steer a
# user who can't see the screen somewhere else (the off-task injection case).
_URL_PATTERN = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|gr|io|info|biz|example)\b")

# Every field the client can speak aloud. safety_flag.reason is spoken for a "caution" in
# English, so it's checked like the rest.
_FREE_TEXT_FIELDS = ("spoken_response", "evidence", "clarifying_question", "camera_feedback", "safety_flag.reason")

_REASSURANCE_MARKERS = tuple(fold(m) for m in ("safe", "no flame", "not burning", "ασφαλ", "χωρίς φωτιά", "δεν καίγεται"))

# Said before a downgraded answer, so a user who can't see the confidence level still hears it.
_HEDGE = {
    "en": "I'm not sure about this.",
    "el": "Δεν είμαι σίγουρος γι' αυτό.",
}

_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
_LATIN = re.compile(r"[A-Za-z]")


def _field_texts(response: dict, field: str) -> list[str]:
    value = response
    for part in field.split("."):
        value = value.get(part) if isinstance(value, dict) else None
        if value is None:
            return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _mostly_not_greek(text: str) -> bool:
    greek = len(_GREEK.findall(text))
    latin = len(_LATIN.findall(text))
    # Short answers and a Latin brand name or two ("Barilla") are fine; a whole English answer
    # to a Greek request is the language-breakout injection.
    return greek + latin >= 12 and greek < latin


def scan_for_injection(response: dict, language: str | None = None) -> list[str]:
    """Returns the checks that tripped (empty list = clean): a meta-instruction marker or a web
    address in any spoken field, or - for a Greek request - a spoken answer that isn't Greek."""
    flagged: list[str] = []
    for field in _FREE_TEXT_FIELDS:
        for text in _field_texts(response, field):
            folded = fold(text)
            if any(p.search(folded) for p in _MARKER_PATTERNS):
                flagged.append(field)
                break
            if _URL_PATTERN.search(folded):
                flagged.append(f"{field}:url")
                break
    if language == "el":
        # camera_feedback is spoken too ("turn on the light"): an English one reaches a Greek cook
        # who may not understand it at all - seen live with Gemini.
        for field in ("spoken_response", "camera_feedback"):
            if _mostly_not_greek(str(response.get(field) or "")):
                flagged.append(f"{field}:language")
    return flagged


def log_flagged_response(reasons: list[str], response: dict, context: dict) -> None:
    """Not blocking, just makes flagged events visible after the fact. Never
    logs the raw image or its base64 encoding - only investigative context
    (recipe_id/step_index/mode/language) and which check(s) tripped."""
    logger.warning(
        "output_guard flagged response: checks=%s mode=%s recipe_id=%s step_index=%s language=%s",
        reasons,
        context.get("mode"),
        context.get("recipe_id"),
        context.get("step_index"),
        context.get("language"),
    )


def sanitize_response(response: dict, language: str, context: dict | None = None) -> dict:
    """If scan_for_injection() finds anything, replace the response with
    the existing schema-valid fallback (reuses vision._fallback_response)
    rather than trying to salvage the good fields - a response that trips a
    safety heuristic should degrade the same way a failed API call already
    does, using a path that's already tested."""
    reasons = scan_for_injection(response, language)
    if not reasons:
        return response

    log_flagged_response(reasons, response, context or {"language": language})
    return vision._fallback_response(language)


def check_confidence_plausibility(response: dict) -> bool:
    """Returns False (implausible) if confidence == "high" but evidence is
    empty, or if safety_flag is None while spoken_response contains
    reassurance language ("safe", "no flame", "not burning") paired with a
    doneness_stage claim - the exact shape of a false-safety-claim
    injection. Deliberately conservative: callers downgrade rather than
    discard the response outright - a plausibility miss is a much weaker
    signal than a detected injection marker, and over-triggering here just
    makes the app hedge more often, the same safe failure mode
    confidence="low" already has everywhere else."""
    if response.get("confidence") == "high" and not response.get("evidence"):
        return False

    spoken = fold(str(response.get("spoken_response") or ""))
    has_reassurance = any(marker in spoken for marker in _REASSURANCE_MARKERS)
    if has_reassurance and response.get("safety_flag") is None and response.get("doneness_stage"):
        return False

    return True


def apply_plausibility_check(response: dict, context: dict | None = None) -> dict:
    """Second, softer pass after sanitize_response - downgrades rather than
    discards a response that fails check_confidence_plausibility(). The downgrade is
    made audible: a user who can't see the screen only ever hears spoken_response, so a
    lowered confidence field alone would change nothing they experience."""
    if check_confidence_plausibility(response):
        return response

    context = context or {}
    log_flagged_response(["implausible_confidence"], response, context)
    response = dict(response)
    response["confidence"] = "low"
    response["needs_clarification"] = True
    hedge = _HEDGE.get(context.get("language") or "el", _HEDGE["en"])
    spoken = str(response.get("spoken_response") or "").strip()
    if not spoken.startswith(hedge):
        response["spoken_response"] = f"{hedge} {spoken}".strip()
    return response
