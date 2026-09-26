"""Hand detection via MediaPipe Hand Landmarker (pretrained, Apache-2.0). 21 landmarks per
hand; the five fingertips are what make "touching X" answerable rather than just "near X".

Needs the optional requirements-detect.txt; import this module lazily.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .detector import MODELS_DIR

HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
HAND_MODEL_PATH = MODELS_DIR / "hand_landmarker.task"
FINGERTIP_LANDMARKS = (4, 8, 12, 16, 20)  # thumb, index, middle, ring, pinky tips
# Landmarks sit on joints and fingertips; a padded hull is closer to what a human boxes as "hand".
BOX_PAD = 0.15


@dataclass
class Hand:
    handedness: str  # "Left" / "Right", as MediaPipe reports it for the image
    confidence: float
    box: tuple[float, float, float, float]  # normalized x1, y1, x2, y2
    fingertips: list[tuple[float, float]] = field(default_factory=list)


def merge_hands(landmarked: list[Hand], detector_boxes: list[tuple[tuple, float]], iou_thr: float = 0.3) -> list[Hand]:
    """Hybrid hands: MediaPipe's (with fingertips) plus any hand the object detector found that
    MediaPipe didn't - typically a hand cut off at the frame edge or seen edge-on, where the
    palm detector gives up. Those come back box-only (no fingertips), so relations for them
    fall back to box overlap."""
    from .metrics import iou

    merged = list(landmarked)
    for box, confidence in sorted(detector_boxes, key=lambda b: -b[1]):
        if all(iou(box, h.box) < iou_thr for h in merged):
            merged.append(Hand(handedness="Unknown", confidence=confidence, box=box))
    return merged


def ensure_hand_model(path: Path = HAND_MODEL_PATH) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    import httpx

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with httpx.stream("GET", HAND_MODEL_URL, timeout=60.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes(1 << 16):
                fh.write(chunk)
    tmp.replace(path)
    return path


def landmarks_to_box(xs: list[float], ys: list[float], pad: float = BOX_PAD) -> tuple[float, float, float, float]:
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    return (max(0.0, x1 - px), max(0.0, y1 - py), min(1.0, x2 + px), min(1.0, y2 + py))


class HandTracker:
    """Stateless per-frame (IMAGE mode): simplest correct option while several clients may
    share one backend. VIDEO mode would add temporal tracking if a single stream needs it."""

    def __init__(self, model_path: Optional[Path] = None, num_hands: int = 2, min_confidence: float = 0.5):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path or ensure_hand_model())),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=num_hands,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def detect(self, image_bgr) -> list[Hand]:
        import numpy as np

        rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)
        hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            xs = [lm.x for lm in landmarks]
            ys = [lm.y for lm in landmarks]
            best = handedness[0] if handedness else None
            hands.append(Hand(
                handedness=best.category_name if best else "Unknown",
                confidence=float(best.score) if best else 0.0,
                box=landmarks_to_box(xs, ys),
                fingertips=[(min(1.0, max(0.0, xs[i])), min(1.0, max(0.0, ys[i]))) for i in FINGERTIP_LANDMARKS],
            ))
        return hands

    def close(self) -> None:
        self._landmarker.close()
