#!/usr/bin/env python3
"""Install a reference photo for a recipe step, or list reference slot status.

Usage:
  python scripts/add_reference.py <recipe_id> <step_index> <photo>
  python scripts/add_reference.py --list
"""
import io
import sys
from pathlib import Path

from PIL import Image, ImageOps

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import recipes  # noqa: E402

REFERENCE_DIR = BACKEND_DIR / "data" / "reference_images"

QUALITY_STEPS = (85, 80, 72, 65, 55)
MAX_BYTES = 200 * 1024
MAX_EDGE = 1024


def list_slots() -> int:
    recipes.load_recipes()
    print(f"{'recipe':<16} {'step':<5} {'reference_image':<32} {'status':<10} size")
    for recipe in recipes.all_recipes():
        for step in recipe.steps:
            if not step.reference_image:
                continue
            full = REFERENCE_DIR / step.reference_image
            if full.is_file():
                status = "present"
                size_str = f"{full.stat().st_size / 1024:.1f} KB"
            else:
                status = "MISSING"
                size_str = "-"
            print(f"{recipe.id:<16} {step.index:<5} {step.reference_image:<32} {status:<10} {size_str}")
    return 0


def add_reference(recipe_id: str, step_index: int, photo_path: Path) -> int:
    recipes.load_recipes()
    rel_path = recipes.reference_image_path(recipe_id, step_index)
    if not rel_path:
        print(f"ERROR: {recipe_id}/step {step_index} does not declare a reference_image in recipes.json", file=sys.stderr)
        return 1

    if not photo_path.is_file():
        print(f"ERROR: photo not found: {photo_path}", file=sys.stderr)
        return 1

    before_size = photo_path.stat().st_size

    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img)  # bake in phone EXIF rotation before dropping the flag
    img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    final_bytes = b""
    final_quality = None
    for quality in QUALITY_STEPS:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        final_bytes = data
        final_quality = quality
        if len(data) <= MAX_BYTES:
            break

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REFERENCE_DIR / rel_path
    out_path.write_bytes(final_bytes)
    after_size = len(final_bytes)

    print(f"Installed reference image: {out_path}")
    print(f"Before: {before_size / 1024:.1f} KB -> After: {after_size / 1024:.1f} KB (quality={final_quality})")
    if after_size > MAX_BYTES:
        print(f"WARNING: still over 200KB even at the lowest quality step ({QUALITY_STEPS[-1]})")

    print(f"Verify: curl -I http://localhost:8000/reference/{recipe_id}/{step_index}")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        return list_slots()

    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 1

    recipe_id = sys.argv[1]
    try:
        step_index = int(sys.argv[2])
    except ValueError:
        print(f"ERROR: step_index must be an integer, got {sys.argv[2]!r}", file=sys.stderr)
        return 1
    photo_path = Path(sys.argv[3])

    return add_reference(recipe_id, step_index, photo_path)


if __name__ == "__main__":
    sys.exit(main())
