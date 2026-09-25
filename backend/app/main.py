import base64
import logging
import mimetypes
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, barcode, demo_cache, output_guard, rate_limit, recipes, vision
from .schemas import AnalyzeRequest, AnalyzeResponse, Recipe

logger = logging.getLogger(__name__)

# Windows registers .js as text/plain, which makes browsers refuse to execute ES modules served that way.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Base64 overhead plus a large photo, well above capture.js's own MAX_EDGE/QUALITY-constrained output.
MAX_ANALYZE_CONTENT_LENGTH = 15 * 1024 * 1024
# Checked again after decoding, since a pathological base64 string could slip past a
# Content-Length check depending on how it's encoded.
MAX_DECODED_IMAGE_BYTES = 10 * 1024 * 1024

app = FastAPI()


@app.middleware("http")
async def _limit_analyze_content_length(request: Request, call_next):
    if request.url.path == "/analyze":
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_ANALYZE_CONTENT_LENGTH:
            return JSONResponse(status_code=413, content={"detail": "request body too large"})
    return await call_next(request)

THERMOMETER_NOTE = {
    "en": (
        "Do not judge raw meat, poultry, fish or eggs by appearance. Use a food thermometer: "
        "74°C/165°F for poultry, 71°C/160°F for ground meat and eggs, 63°C/145°F for whole cuts "
        "of beef, pork and fish."
    ),
    "el": (
        "Μην κρίνεις ωμό κρέας, κοτόπουλο, ψάρι ή αυγά από την εμφάνιση. Χρησιμοποίησε θερμόμετρο "
        "τροφίμων: 74°C για πουλερικά, 71°C για κιμά και αυγά, 63°C για ολόκληρα κομμάτια "
        "βοδινού, χοιρινού και ψαριού."
    ),
}

_ALARM_KEYWORDS = ("flame", "fire", "burning", "burnt", "burned", "char", "scorch", "blacken", "spark", "melting")
_ALARM_VETO = ("steam", "haze", "vapor", "vapour", "condensation")

# Checked in this order: anthropic -> ANTHROPIC_API_KEY, openai -> OPENAI_API_KEY, gemini -> GEMINI_API_KEY or GOOGLE_API_KEY.
PROVIDER_KEY_ENV = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}

# /analyze is the expensive one (a real vision-provider call); /barcode is cheaper but
# still an open proxy to a third party, whose own rate limit is a shared resource.
ANALYZE_RATE_LIMIT = (20, 3600.0)  # (max_requests, window_sec)
BARCODE_RATE_LIMIT = (60, 3600.0)


def _rate_limit_dependency(prefix: str, max_requests: int, window_sec: float):
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limit.check_rate_limit(f"{prefix}:{client_ip}", max_requests=max_requests, window_sec=window_sec):
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded, try again later",
                headers={"Retry-After": str(int(window_sec))},
            )

    return dependency


def _apply_protein_safety(response: dict, mode: str, language: str, recipe_flagged) -> dict:
    triggered = bool(response.get("raw_protein_detected")) if recipe_flagged is None else recipe_flagged
    if not triggered:
        return response

    note = THERMOMETER_NOTE.get(language, THERMOMETER_NOTE["en"])
    response = dict(response)
    if mode == "check_doneness":
        response["doneness_stage"] = None
        response["confidence"] = "low"
        response["evidence"] = []
        response["needs_clarification"] = False
        response["clarifying_question"] = None
        response["spoken_response"] = note
    else:
        # "what is this package" still deserves an answer, not only a lecture.
        response["spoken_response"] = f"{response.get('spoken_response', '')} {note}".strip()
    return response


def _apply_safety_flag(response: dict) -> dict:
    flag = response.get("safety_flag")
    if not flag or flag.get("severity") != "alarm":
        return response

    reason = (flag.get("reason") or "").lower()
    has_alarm_keyword = any(kw in reason for kw in _ALARM_KEYWORDS)
    has_veto = any(v in reason for v in _ALARM_VETO)

    if has_alarm_keyword and not has_veto:
        return response

    response = dict(response)
    response["safety_flag"] = {**flag, "severity": "caution"}
    return response


def _apply_safety_rules(response: dict, req: AnalyzeRequest, recipe_flagged) -> dict:
    guard_context = {
        "mode": req.mode,
        "language": req.language,
        "recipe_id": req.recipe_id,
        "step_index": req.step_index,
    }
    # sanitize_response runs first so every path (fixture and live) is covered, not just callers that remember to.
    response = output_guard.sanitize_response(response, req.language, guard_context)
    response = output_guard.apply_plausibility_check(response, guard_context)
    response = _apply_protein_safety(response, req.mode, req.language, recipe_flagged)
    return _apply_safety_flag(response)


def _canned_demo_miss(language: str) -> dict:
    text = (
        "Δεν βρέθηκε δείγμα επίδειξης για αυτό το βήμα."
        if language == "el"
        else "No demo fixture found for this step."
    )
    return AnalyzeResponse(
        description="",
        primary_subject="",
        confidence="low",
        spoken_response=text,
    ).model_dump()


@app.on_event("startup")
def on_startup():
    recipes.load_recipes()
    if demo_cache.demo_mode_enabled():
        return
    provider = os.getenv("VISION_PROVIDER", "anthropic")
    key_envs = PROVIDER_KEY_ENV.get(provider)
    if key_envs is None:
        logger.warning("Unrecognized VISION_PROVIDER: %s", provider)
        return
    if not any(os.getenv(var) for var in key_envs):
        logger.warning("VISION_PROVIDER=%s but none of %s is set", provider, key_envs)


@app.get("/health")
def health():
    return {"status": "ok", "demo_mode": demo_cache.demo_mode_enabled()}


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    dependencies=[
        Depends(auth.require_pairing_token),
        Depends(_rate_limit_dependency("analyze", *ANALYZE_RATE_LIMIT)),
    ],
)
def analyze(req: AnalyzeRequest):
    recipe_flagged = recipes.step_contains_raw_protein(req.recipe_id, req.step_index)

    if demo_cache.demo_mode_enabled():
        fixture = demo_cache.load_fixture(req.mode, req.recipe_id, req.step_index)
        if fixture is not None:
            return _apply_safety_rules(fixture, req, recipe_flagged)
        if demo_cache.demo_strict_enabled():
            canned = _canned_demo_miss(req.language)
            return _apply_safety_rules(canned, req, recipe_flagged)
        # DEMO_MODE without DEMO_STRICT falls through to a live call on a fixture miss.

    try:
        image_bytes = base64.standard_b64decode(req.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid base64 image")

    if len(image_bytes) > MAX_DECODED_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="decoded image too large")

    context = {
        "mode": req.mode,
        "detail_level": req.detail_level,
        "language": req.language,
        "recipe_id": req.recipe_id,
        "step_index": req.step_index,
        "prior_context": req.prior_context,
        "user_followup": req.user_followup,
    }

    result = vision.analyze_frame(image_bytes, context)
    return _apply_safety_rules(result, req, recipe_flagged)


@app.get("/recipes", dependencies=[Depends(auth.require_pairing_token)])
def list_recipes():
    return [{"id": r.id, "name": r.name} for r in recipes.all_recipes()]


@app.get("/recipes/{recipe_id}", response_model=Recipe, dependencies=[Depends(auth.require_pairing_token)])
def get_recipe_detail(recipe_id: str):
    recipe = recipes.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return recipe


@app.get(
    "/barcode/{code}",
    dependencies=[
        Depends(auth.require_pairing_token),
        Depends(_rate_limit_dependency("barcode", *BARCODE_RATE_LIMIT)),
    ],
)
async def get_barcode(code: str):
    product = await barcode.lookup_barcode(code)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@app.get("/reference/{recipe_id}/{step_index}", dependencies=[Depends(auth.require_pairing_token)])
def get_reference(recipe_id: str, step_index: int):
    rel_path = recipes.reference_image_path(recipe_id, step_index)
    if not rel_path:
        raise HTTPException(status_code=404, detail="no reference image for this step")
    full_path = DATA_DIR / "reference_images" / rel_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"reference image not on disk: {rel_path}")
    return FileResponse(full_path)


# Mounted last: mounting at "/" before the routes above would shadow every one of them.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
