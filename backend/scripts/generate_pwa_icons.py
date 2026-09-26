#!/usr/bin/env python3
"""Generate placeholder PWA icons. Not final branding - replace the PNGs when a real mark exists.

  python scripts/generate_pwa_icons.py

Writes icon-192.png, icon-512.png, and icon-512-maskable.png into backend/static/icons/.
The maskable variant keeps the mark inside the inner 80% circle Android uses when it
crops the icon to a squircle.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BACKEND_DIR = Path(__file__).resolve().parent.parent
ICONS_DIR = BACKEND_DIR / "static" / "icons"

BG = (17, 17, 17)  # matches app.css --bg / the manifest theme_color
ACCENT = (255, 212, 0)  # app.css --accent


def _draw_pan(draw: ImageDraw.ImageDraw, size: int, inset_ratio: float) -> None:
    """A yellow pan: circle plus a short handle, inset so maskable crop keeps it."""
    inset = int(size * inset_ratio)
    box = (inset, inset, size - inset, size - inset)
    draw.ellipse(box, fill=ACCENT)
    # hollow centre so it reads as a pan, not a blob
    hole = int(size * (inset_ratio + 0.12))
    draw.ellipse((hole, hole, size - hole, size - hole), fill=BG)
    # Handle lives in the ring at 3 o'clock, so a circular maskable crop keeps it.
    handle_w = max(size // 16, 8)
    cy = size // 2
    draw.rounded_rectangle(
        (size - hole, cy - handle_w // 2, size - inset, cy + handle_w // 2),
        radius=handle_w // 2,
        fill=ACCENT,
    )


def render_icon(size: int, *, maskable: bool) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    # Maskable safe zone is a centred circle of diameter 0.8*size. Extra inset (~0.18)
    # keeps the handle inside that circle after a circular crop.
    _draw_pan(draw, size, inset_ratio=0.18 if maskable else 0.10)
    return img


def generate(dest: Path | None = None) -> list[Path]:
    dest = dest or ICONS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name, size, maskable in (
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
    ):
        path = dest / name
        render_icon(size, maskable=maskable).save(path, format="PNG")
        written.append(path)
    return written


def main() -> int:
    paths = generate()
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
