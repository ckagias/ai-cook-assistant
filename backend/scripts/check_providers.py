#!/usr/bin/env python3
"""Verify each configured vision provider actually works.

Usage: python scripts/check_providers.py [photo.jpg]
"""
import io
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import recipes, vision  # noqa: E402
from app.schemas import AnalyzeResponse  # noqa: E402

PROVIDERS = ["anthropic", "openai", "gemini"]

KEY_ENV_VARS = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
}

_CALL_FUNCS = {
    "anthropic": vision._call_anthropic,
    "openai": vision._call_openai,
    "gemini": vision._call_gemini,
}


def get_key(provider: str) -> str | None:
    for var in KEY_ENV_VARS[provider]:
        val = os.getenv(var)
        if val:
            return val
    return None


def make_synthetic_pan_photo() -> bytes:
    img = Image.new("RGB", (800, 600), color=(60, 55, 50))  # dark countertop
    draw = ImageDraw.Draw(img)
    draw.ellipse([150, 100, 650, 500], fill=(70, 70, 72))  # pan
    draw.ellipse([250, 200, 550, 400], fill=(180, 130, 70))  # golden-brown food
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def check_reference_photo_presence() -> None:
    rel = recipes.reference_image_path("pancakes", 2)
    if not rel:
        print("Pancake reference image: not declared in recipes.json")
        return
    full = BACKEND_DIR / "data" / "reference_images" / rel
    if full.is_file():
        print(f"Pancake reference image: present at {full}")
    else:
        print(f"Pancake reference image: MISSING at {full} (the reference-photo comparison will be silently skipped)")


def list_models(provider: str) -> list[str]:
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        return [m.id for m in client.models.list().data]
    if provider == "openai":
        import openai

        client = openai.OpenAI()
        return [m.id for m in client.models.list().data]
    if provider == "gemini":
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        return [m.name for m in client.models.list()]
    return []


def run_check_doneness(provider: str, image_bytes: bytes) -> AnalyzeResponse:
    # Calls the provider function directly (not vision.analyze_frame), which
    # swallows every exception into a schema-valid fallback - that would make
    # every provider look "fine" even when its credential is dead, defeating
    # the whole point of this script.
    context = {
        "mode": "check_doneness",
        "detail_level": "brief",
        "language": "el",
        "recipe_id": "pancakes",
        "step_index": 2,
    }
    ref_bytes = vision._reference_image_bytes(context)  # exercises the reference-image path
    user_text = vision._build_user_text(context)
    return _CALL_FUNCS[provider](image_bytes, ref_bytes, user_text)


def check_provider(provider: str, image_bytes: bytes) -> str:
    """Returns "skip", "pass", or "fail"."""
    key = get_key(provider)
    if not key:
        print(f"[{provider}] SKIPPED - no API key configured")
        return "skip"

    print(f"[{provider}] key found, listing available models...")
    try:
        models = list_models(provider)
        shown = ", ".join(models[:5]) + ("..." if len(models) > 5 else "")
        print(f"[{provider}] {len(models)} models available: {shown}")
    except Exception as exc:
        print(f"[{provider}] WARNING: could not list models: {exc}")

    print(f"[{provider}] making a real check_doneness call against pancakes/step 2...")
    start = time.monotonic()
    try:
        result = run_check_doneness(provider, image_bytes)
        elapsed = time.monotonic() - start
        AnalyzeResponse.model_validate(result.model_dump())
        print(f"[{provider}] PASS in {elapsed:.1f}s - confidence={result.confidence}, spoken_response={result.spoken_response!r}")
        return "pass"
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"[{provider}] FAIL after {elapsed:.1f}s: {exc}")
        return "fail"


def main() -> int:
    load_dotenv(BACKEND_DIR / ".env")

    check_reference_photo_presence()
    print()

    if len(sys.argv) > 1:
        photo_path = Path(sys.argv[1])
        image_bytes = photo_path.read_bytes()
        print(f"Using provided test photo: {photo_path}")
    else:
        image_bytes = make_synthetic_pan_photo()
        print("No photo given - synthesized a plausible pan-like test JPEG.")
    print()

    selected = os.getenv("VISION_PROVIDER", "anthropic")
    print(f"VISION_PROVIDER={selected}")
    print()

    results = {}
    for provider in PROVIDERS:
        results[provider] = check_provider(provider, image_bytes)
        print()

    if selected not in PROVIDERS:
        print(f"ERROR: VISION_PROVIDER={selected!r} is not a recognized provider")
        return 1

    status = results[selected]
    if status == "skip":
        print(f"ERROR: the selected provider ({selected}) has no API key configured")
        return 1
    if status == "fail":
        print(f"ERROR: the selected provider ({selected}) failed its check_doneness call")
        return 1

    print(f"OK - the selected provider ({selected}) is working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
