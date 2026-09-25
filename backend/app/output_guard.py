import logging

from . import vision

logger = logging.getLogger(__name__)

# Patterns that suggest the model is reporting on/responding to injected
# instructions rather than describing the photo. Short, reviewed, and
# expected to grow - not a claim of completeness.
_META_INSTRUCTION_MARKERS = (
    "ignore previous",
    "ignore prior",
    "as an ai",
    "i am now",
    "system prompt",
    "you are now",
    "new instructions",
)

_FREE_TEXT_FIELDS = ("spoken_response", "evidence", "clarifying_question")

_REASSURANCE_MARKERS = ("safe", "no flame", "not burning")


def _field_texts(response: dict, field: str) -> list[str]:
    value = response.get(field)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def scan_for_injection(response: dict) -> list[str]:
    """Returns a list of free-text fields that tripped a heuristic check
    (empty list = clean). Checks spoken_response, evidence, and
    clarifying_question - the three free-text fields the model fully
    controls."""
    flagged: list[str] = []
    for field in _FREE_TEXT_FIELDS:
        for text in _field_texts(response, field):
            lowered = text.lower()
            if any(marker in lowered for marker in _META_INSTRUCTION_MARKERS):
                flagged.append(field)
                break
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
    reasons = scan_for_injection(response)
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

    spoken = str(response.get("spoken_response") or "").lower()
    has_reassurance = any(marker in spoken for marker in _REASSURANCE_MARKERS)
    if has_reassurance and response.get("safety_flag") is None and response.get("doneness_stage"):
        return False

    return True


def apply_plausibility_check(response: dict, context: dict | None = None) -> dict:
    """Second, softer pass after sanitize_response - downgrades rather than
    discards a response that fails check_confidence_plausibility()."""
    if check_confidence_plausibility(response):
        return response

    log_flagged_response(["implausible_confidence"], response, context or {})
    response = dict(response)
    response["confidence"] = "low"
    response["needs_clarification"] = True
    return response
