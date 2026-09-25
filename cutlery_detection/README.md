# Cutlery detection

Standalone utility that detects kitchen utensils/cutlery in a photo using a
pretrained YOLOv8 model (COCO classes: bowl, cup, spoon, fork, knife,
bottle). Not wired into the backend.

## Why this isn't imported by `backend/app/main.py`

`ultralytics` and its `torch` dependency pull in roughly 2.5GB, and there's
no dedicated demo beat that needs object detection - the vision model
already describes what it sees in natural language, which is what the app
actually speaks aloud. Adding a hard dependency of that size for a feature
with no demo payoff wasn't worth it.

## Usage

```bash
pip install ultralytics
python detect.py photo.jpg
```

The first run downloads `yolov8n.pt` (~6MB) automatically.

## Wiring it in later

If this turns out to be worth wiring into `scene_description` mode (e.g. to
help enumerate what's on a cluttered counter), the follow-up is small -
roughly 30 minutes:

1. Add `ultralytics` to `backend/requirements.txt`.
2. Import `detect_utensils` from `cutlery_detection/detect.py` inside
   `vision.py`'s `scene_description` handling and fold the result into
   `evidence` or `description`.
3. Accept the first-request latency hit from `torch`/YOLO initializing, or
   warm it at startup behind a feature flag.

Not part of the critical path for the current demo, so left as a standalone
script rather than done speculatively.
