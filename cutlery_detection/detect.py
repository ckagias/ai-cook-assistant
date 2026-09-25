#!/usr/bin/env python3
"""Detect kitchen utensils/cutlery in a photo using a pretrained YOLOv8 model.

Standalone utility - deliberately NOT imported by backend/app/main.py. See
README.md for why.

Usage: python detect.py photo.jpg
"""
import sys

UTENSIL_CLASSES = {"bowl", "cup", "spoon", "fork", "knife", "bottle"}

_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO("yolov8n.pt")  # auto-downloads on first use
    return _model


def detect_utensils(image_path: str) -> list[str]:
    model = _get_model()
    results = model(image_path, verbose=False)

    found = set()
    for result in results:
        for box in result.boxes:
            label = result.names[int(box.cls)]
            if label in UTENSIL_CLASSES:
                found.add(label)

    return sorted(found)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python detect.py photo.jpg", file=sys.stderr)
        return 1

    utensils = detect_utensils(sys.argv[1])
    print(", ".join(utensils) if utensils else "(no utensils detected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
