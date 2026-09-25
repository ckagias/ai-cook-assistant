#!/usr/bin/env python3
"""Record a demo fixture from one real vision call.

Usage: python scripts/record_fixture.py <mode> <photo> [recipe_id] [step_index]
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import vision  # noqa: E402
from app.schemas import AnalyzeResponse  # noqa: E402

FIXTURES_DIR = BACKEND_DIR / "data" / "demo_fixtures"


def main() -> int:
    load_dotenv(BACKEND_DIR / ".env")

    parser = argparse.ArgumentParser(description="Record a demo fixture from a real vision call.")
    parser.add_argument("mode", choices=["identify", "read_label", "check_doneness", "scene_description"])
    parser.add_argument("photo", type=Path)
    parser.add_argument("recipe_id", nargs="?", default=None)
    parser.add_argument("step_index", nargs="?", type=int, default=None)
    args = parser.parse_args()

    if not args.photo.is_file():
        print(f"ERROR: photo not found: {args.photo}", file=sys.stderr)
        return 1

    image_bytes = args.photo.read_bytes()

    # The same recipe/step context enrichment main.py does. Recorded in Greek,
    # since that's the language the demo actually runs in.
    context = {
        "mode": args.mode,
        "detail_level": "brief",
        "language": "el",
        "recipe_id": args.recipe_id,
        "step_index": args.step_index,
        "prior_context": None,
        "user_followup": None,
    }

    print(
        f"Calling the configured vision provider for mode={args.mode!r}, "
        f"recipe_id={args.recipe_id!r}, step_index={args.step_index!r}..."
    )
    result = vision.analyze_frame(image_bytes, context)

    try:
        validated = AnalyzeResponse.model_validate(result)
    except Exception as exc:
        print(f"ERROR: response does not validate against AnalyzeResponse, refusing to write a fixture: {exc}", file=sys.stderr)
        return 1

    if not validated.spoken_response:
        print("ERROR: spoken_response is empty - refusing to write a fixture, it would 500 at demo time", file=sys.stderr)
        return 1

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    if args.recipe_id is not None and args.step_index is not None:
        filename = f"{args.mode}__{args.recipe_id}__{args.step_index}.json"
    else:
        filename = f"{args.mode}.json"
    out_path = FIXTURES_DIR / filename

    out_path.write_text(json.dumps(validated.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"spoken_response: {validated.spoken_response!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
