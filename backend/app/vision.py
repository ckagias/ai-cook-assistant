import base64
import logging
import os
from pathlib import Path
from typing import Optional

from . import recipes as recipes_module
from .schemas import AnalyzeResponse

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent

REFERENCE_NOTE = (
    "The second image is an expert reference photo for this step. "
    "Compare the first (live) image against it."
)

SYSTEM_PROMPT = """You are a voice-first cooking assistant for a user who cannot look at the screen.

Never assume the user can look at anything. Give actionable directions ("tilt the phone down toward the pan"), never visual references ("as you can see").

If the frame is bad or unreadable, set camera_feedback to one short corrective instruction and keep every other field minimal.

Calibrate confidence honestly. Only use "high" when the answer is unambiguous.

evidence: up to 3 short observed features you actually saw. Never invent evidence.

When confidence is not "high": hedge spoken_response, set needs_clarification=true, and ask one simple, non-visual clarifying_question (about smell, sound, touch, or time), never a visual one.

Word-budget spoken_response by word count, not characters, since Greek runs longer per word: about 15-25 words when detail_level is "brief", about 60 words when detail_level is "detailed".

If language is "el": write spoken_response, clarifying_question, and evidence in Greek. confidence, doneness_stage, and safety_flag.severity must stay their English enum values regardless of language.

If a second (reference) image is present, explicitly compare the live image against it.

Set raw_protein_detected=true generously whenever raw or undercooked poultry, pork, eggs, or fish might be present. You are never the final safety authority on this, so a false positive is cheap and a false negative is not.

Set safety_flag.severity="alarm" only for unambiguous danger such as a visible flame or blackening/char. Use "caution" for ambiguous cues like steam or haze. safety_flag.reason is always in English regardless of the response language, since it is backend-facing only and never spoken aloud.

Never say "as shown" or "you can see"."""

_TRANSIENT_MARKERS = ("503", "unavailable", "429", "resource_exhausted", "overloaded")


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _fallback_response(language: str) -> dict:
    apology = (
        "Συγγνώμη, κάτι πήγε στραβά. Δοκίμασε ξανά."
        if language == "el"
        else "Sorry, something went wrong. Please try again."
    )
    return AnalyzeResponse(
        description="",
        primary_subject="",
        camera_feedback=None,
        doneness_stage=None,
        confidence="low",
        evidence=[],
        alternate_guesses=[],
        needs_clarification=False,
        clarifying_question=None,
        raw_protein_detected=False,
        safety_flag=None,
        spoken_response=apology,
    ).model_dump()


def _reference_image_bytes(context: dict) -> Optional[bytes]:
    recipe_id = context.get("recipe_id")
    step_index = context.get("step_index")
    if recipe_id is None or step_index is None:
        return None
    rel_path = recipes_module.reference_image_path(recipe_id, step_index)
    if not rel_path:
        return None
    full_path = BACKEND_ROOT / "data" / "reference_images" / rel_path
    if not full_path.is_file():
        return None
    try:
        return full_path.read_bytes()
    except OSError:
        return None


def _build_user_text(context: dict) -> str:
    lines = [
        f"Mode: {context.get('mode')}",
        f"Detail level: {context.get('detail_level', 'brief')}",
        f"Language: {context.get('language', 'el')}",
    ]

    recipe_id = context.get("recipe_id")
    step_index = context.get("step_index")
    if recipe_id is not None and step_index is not None:
        lines.append(f"Recipe: {recipe_id}, step {step_index}")
        step = recipes_module.get_step(recipe_id, step_index)
        if step is not None:
            instruction = step.instruction.get(context.get("language", "el")) or step.instruction.get("en")
            if instruction:
                lines.append(f"Step instruction: {instruction}")
            if step.check_prompt_hint:
                lines.append(f"What to check: {step.check_prompt_hint}")

    prior_context = context.get("prior_context")
    if prior_context:
        lines.append(f"Prior context: {prior_context}")

    user_followup = context.get("user_followup")
    if user_followup:
        lines.append(f"User follow-up: {user_followup}")

    return "\n".join(lines)


def _call_anthropic(image_bytes: bytes, ref_bytes: Optional[bytes], user_text: str) -> AnalyzeResponse:
    import anthropic

    client = anthropic.Anthropic(timeout=20.0, max_retries=1)

    content = [
        {"type": "text", "text": user_text},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(image_bytes).decode("ascii"),
            },
        },
    ]
    if ref_bytes is not None:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(ref_bytes).decode("ascii"),
                },
            }
        )
        content.append({"type": "text", "text": REFERENCE_NOTE})

    result = client.messages.parse(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        output_format=AnalyzeResponse,
        messages=[{"role": "user", "content": content}],
    )
    return result.output_parsed


def _call_openai(image_bytes: bytes, ref_bytes: Optional[bytes], user_text: str) -> AnalyzeResponse:
    import openai

    client = openai.OpenAI(timeout=20.0, max_retries=1)

    content = [
        {"type": "input_text", "text": user_text},
        {
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{base64.standard_b64encode(image_bytes).decode('ascii')}",
        },
    ]
    if ref_bytes is not None:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{base64.standard_b64encode(ref_bytes).decode('ascii')}",
            }
        )
        content.append({"type": "input_text", "text": REFERENCE_NOTE})

    kwargs = dict(
        model=os.getenv("OPENAI_MODEL", "gpt-5"),
        instructions=SYSTEM_PROMPT,
        input=[{"role": "user", "content": content}],
        text_format=AnalyzeResponse,
        max_output_tokens=8192,
    )
    # Only non-reasoning models 400 on `reasoning` - default effort stays on, but let it be disabled explicitly.
    reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "low")
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}

    result = client.responses.parse(**kwargs)
    return result.output_parsed


def _call_gemini(image_bytes: bytes, ref_bytes: Optional[bytes], user_text: str) -> AnalyzeResponse:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=20_000))

    parts = [
        types.Part.from_text(text=user_text),
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
    ]
    if ref_bytes is not None:
        parts.append(types.Part.from_bytes(data=ref_bytes, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=REFERENCE_NOTE))

    models = [
        m.strip()
        for m in os.getenv("GEMINI_MODEL", "gemini-3.7-flash,gemini-3.8-flash,gemini-3.6-flash").split(",")
        if m.strip()
    ]

    last_exc: Optional[Exception] = None
    for i, model_name in enumerate(models):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=parts,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_schema=AnalyzeResponse,
                    response_mime_type="application/json",
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            return AnalyzeResponse.model_validate_json(response.text)
        except Exception as exc:
            last_exc = exc
            is_last = i == len(models) - 1
            if is_last or not _is_transient_error(exc):
                raise
            logger.warning("Gemini model %s failed transiently, trying next: %s", model_name, exc)
    raise last_exc


_PROVIDER_CALLS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
}


def analyze_frame(image_bytes: bytes, context: dict) -> dict:
    language = context.get("language", "el")
    provider = os.getenv("VISION_PROVIDER", "anthropic")
    call = _PROVIDER_CALLS.get(provider)

    if call is None:
        logger.error("Unknown VISION_PROVIDER: %s", provider)
        return _fallback_response(language)

    parsed = None
    try:
        ref_bytes = _reference_image_bytes(context)
        user_text = _build_user_text(context)
        parsed = call(image_bytes, ref_bytes, user_text)
    except Exception:
        logger.exception("Vision provider %s failed", provider)

    if parsed is None:
        return _fallback_response(language)

    result = parsed.model_dump()
    result["evidence"] = list(result.get("evidence") or [])[:3]
    return result
