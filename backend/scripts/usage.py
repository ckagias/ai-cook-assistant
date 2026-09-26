#!/usr/bin/env python3
"""Printed at the end of setup.sh / setup.ps1: where to open the app, what it does, how to use
it, and the live status of this install. One source, so both setup scripts say the same thing.

Usage: python scripts/usage.py [--shell sh|ps] [--python <venv python path as the user types it>]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

LINE = "=" * 72


def read_env() -> dict:
    try:
        from dotenv import dotenv_values

        return {k: (v or "") for k, v in dotenv_values(BACKEND_DIR / ".env").items()}
    except ImportError:
        return {}


def ai_status(env: dict) -> str:
    keys = {"anthropic": ["ANTHROPIC_API_KEY"], "openai": ["OPENAI_API_KEY"], "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]}
    provider = env.get("VISION_PROVIDER", "anthropic")
    needed = keys.get(provider)
    if needed is None:
        return f"unknown VISION_PROVIDER '{provider}' - use anthropic, openai or gemini in backend/.env"
    if any(env.get(k) for k in needed):
        return f"{provider}, key set"
    return f"{provider}, NO KEY - add {' or '.join(needed)} to backend/.env (the two AI buttons need it)"


def detection_status(env: dict, shell: str) -> list[str]:
    installed = importlib.util.find_spec("ultralytics") and importlib.util.find_spec("mediapipe")
    if not installed:
        flag = "-NoDetection" if shell == "ps" else "--no-detection"
        return [f"not installed (setup ran with {flag}, or Python isn't 3.11/3.12)"]
    model = f"{env.get('DETECTOR_MODEL', 'yoloe-26s-seg')} @{env.get('DETECTOR_IMGSZ', '480')}, {env.get('DETECTOR_FORMAT', 'openvino')}"
    if env.get("DETECTION_ENABLED", "false").lower() == "true":
        return [f"installed and on ({model})"]
    return [f"installed ({model}); setup-window turns it on,",
            "               plain --run doesn't: set DETECTION_ENABLED=true in backend/.env"]


def recipe_status(env: dict) -> str:
    if env.get("DB_PATH"):
        os.environ.setdefault("DB_PATH", env["DB_PATH"])
    try:
        from app import recipes

        published = len(recipes.all_recipes())
        staged = len(recipes.all_recipes(status=recipes.STAGED))
    except Exception as exc:  # the summary must never make setup look failed
        return f"database not readable ({type(exc).__name__})"
    return f"{published} ready to cook, {staged} imported and waiting for review"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shell", choices=["sh", "ps"], default="sh")
    ap.add_argument("--python", default=None, help="venv python path as the user would type it")
    args = ap.parse_args()

    env = read_env()
    ps = args.shell == "ps"
    py = args.python or (r"backend\.venv\Scripts\python.exe" if ps else "backend/.venv/bin/python")
    scripts = r"backend\scripts" if ps else "backend/scripts"
    sep = "\\" if ps else "/"
    port = env.get("BACKEND_PORT") or "8000"
    token = env.get("BACKEND_PAIRING_TOKEN", "")
    local_url = f"http://localhost:{port}/" + (f"?token={token}" if token else "")
    run_cmd = r".\setup.ps1 -Run" if ps else "./setup.sh --run"
    window_cmd = r".\setup-window.cmd" if ps else "./setup-window.sh"

    out = [
        "",
        LINE,
        "  Cooking Assistant (Βοηθός Μαγειρικής) - setup finished",
        LINE,
        "",
        "WHAT IT DOES",
        "  A voice-first cooking helper for a phone or tablet propped up in the kitchen,",
        "  made for cooks who can't (or don't want to) look at the screen while cooking.",
        "  - Point the camera at food or a package: it says out loud what it sees.",
        "  - Recipes step by step, read aloud, with timers that start by themselves.",
        "  - \"Is it ready?\" from a photo, with food-safety rules for raw meat, eggs and fish.",
        "  - Live detection: boxes around utensils, cookware, ingredients and hands, and",
        "    which hand is touching what (shown on screen only - the camera has no depth).",
        "  Speaks Greek by default; English if the device has no Greek voice.",
        "",
        "OPEN IT",
        f"  On this computer:   {run_cmd}",
        f"                      then open  {local_url}",
        f"  Phones and tablets: {window_cmd}",
        "                      (serves it on your Wi-Fi over HTTPS, opens an app window here,",
        "                      and prints the link to open on the phone)",
        f"  Android over USB:   adb reverse tcp:{port} tcp:{port}, then the localhost link above",
        "",
        "HOW TO USE IT",
        "  1. ΞΕΚΙΝΑ (Start)        allows camera, microphone and sound - tap it first",
        "  2. Τι είναι αυτό;        \"What is this?\" - takes a photo, says what it sees",
        "  3. Συνταγές              \"Recipes\" - pick one; each step is read aloud",
        "       Είναι έτοιμο;       \"Is it ready?\" - checks the food from a photo",
        "       Επανάλαβε           repeat the current step",
        "       Επόμενο / Διακοπή   next step / stop the recipe",
        "  4. Ανίχνευση             \"Detection\" - live boxes and a table under the camera",
        "  Not sure what a button does? Long-press it (phone) or hover over it (computer):",
        "  it tells you, without pressing it. A Bluetooth remote or keyboard works too:",
        "  Space/Enter = check or identify, right arrow = next step.",
        "",
        "STATUS",
        f"  AI answers:  {ai_status(env)}",
    ]
    detection = detection_status(env, args.shell)
    out.append(f"  Detection:   {detection[0]}")
    out += detection[1:]
    out += [
        f"  Recipes:     {recipe_status(env)}",
        "  Pairing:     " + ("on - a device needs the ?token=... link once" if token
                             else "off - anyone who can reach the server can use it"),
        "",
        "MORE",
        f"  Import a recipe:  {py} {scripts}{sep}import_recipes.py url --urls <recipe page URL>",
        f"  Review imports:   {py} {scripts}{sep}curate_recipe.py --list",
        f"  Test the AI key:  {py} {scripts}{sep}check_providers.py",
        "  Details:          README.md",
        LINE,
        "",
    ]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
