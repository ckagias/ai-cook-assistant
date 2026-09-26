"""The /detect pipeline: decode JPEG -> objects -> hands -> hand/object relations.

Configured from the environment (see .env.example). The heavy imports happen on first
use, so with DETECTION_ENABLED unset the base app never touches ultralytics/mediapipe.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .relations import hand_object_relations
from .vocabulary import Vocabulary, load_vocabulary

logger = logging.getLogger(__name__)

# mediapipe: landmarked hands (fingertips -> "touching"); detector: the object model's hand boxes;
# hybrid: MediaPipe's hands plus any hand box only the detector found (edge-of-frame, edge-on).
HANDS_BACKENDS = ("mediapipe", "hybrid", "detector", "none")


class DetectionUnavailable(RuntimeError):
    """Detection is switched off or its optional dependencies aren't installed -> HTTP 503."""


def detection_enabled() -> bool:
    return os.getenv("DETECTION_ENABLED", "false").lower() == "true"


@dataclass
class DetectionConfig:
    # Defaults = the measured winner on the reference laptop (data/benchmarks/detector_report.md).
    model: str = "yoloe-26s-seg"
    imgsz: int = 480
    fmt: str = "openvino"
    conf: float = 0.25
    hands: str = "hybrid"

    @classmethod
    def from_env(cls) -> "DetectionConfig":
        cfg = cls(
            model=os.getenv("DETECTOR_MODEL", cls.model),
            imgsz=int(os.getenv("DETECTOR_IMGSZ", cls.imgsz)),
            fmt=os.getenv("DETECTOR_FORMAT", cls.fmt),
            conf=float(os.getenv("DETECTOR_CONF", cls.conf)),
            hands=os.getenv("HANDS_BACKEND", cls.hands),
        )
        if cfg.hands not in HANDS_BACKENDS:
            raise DetectionUnavailable(f"HANDS_BACKEND must be one of {HANDS_BACKENDS}, got {cfg.hands!r}")
        return cfg


@dataclass
class _DetectorHand:
    """A hand box from the object detector itself (HANDS_BACKEND=detector) - no landmarks."""

    box: tuple
    confidence: float
    handedness: str = "Unknown"
    fingertips: list = field(default_factory=list)


class DetectionService:
    def __init__(self, config: DetectionConfig, vocab: Optional[Vocabulary] = None):
        self.config = config
        self.vocab = vocab or load_vocabulary()
        self._lock = threading.Lock()  # neither model is safe to call from two threads at once
        self._detector = None
        self._hands = None

    @property
    def label(self) -> str:
        c = self.config
        return f"{c.model}@{c.imgsz}/{c.fmt}+hands:{c.hands}"

    def _ensure_loaded(self) -> None:
        if self._detector is not None:
            return
        try:
            from .detector import load_detector

            t0 = time.perf_counter()
            self._detector = load_detector(self.config.model, self.config.imgsz, self.config.fmt, self.vocab)
            if self.config.hands in ("mediapipe", "hybrid"):
                from .hands import HandTracker

                self._hands = HandTracker()
            logger.info("detection ready: %s in %.1fs", self.label, time.perf_counter() - t0)
        except ImportError as exc:
            raise DetectionUnavailable(
                f"detection dependencies missing ({exc.name}) - install backend/requirements-detect.txt"
            ) from exc

    def warm(self) -> None:
        try:
            with self._lock:
                self._ensure_loaded()
        except Exception:
            logger.exception("detection warm-up failed; /detect will retry on first request")

    def run(self, jpeg: bytes, allowed_ids: Optional[set[str]] = None) -> dict:
        import cv2
        import numpy as np

        t0 = time.perf_counter()
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("body is not a decodable image")
        height, width = image.shape[:2]
        t1 = time.perf_counter()

        with self._lock:
            self._ensure_loaded()
            # Waiting for another frame (or the first-time model load) is "queue", not inference.
            t_start = time.perf_counter()
            detections = self._detector.detect(image, self.config.conf)
            t2 = time.perf_counter()
            if self.config.hands == "mediapipe":
                hands = self._hands.detect(image)
            elif self.config.hands == "hybrid":
                from .hands import merge_hands

                boxes = [(d.box, d.confidence) for d in detections if d.class_id == "hand"]
                hands = merge_hands(self._hands.detect(image), boxes)
            elif self.config.hands == "detector":
                hands = [_DetectorHand(d.box, d.confidence) for d in detections if d.class_id == "hand"]
            else:
                hands = []
            t3 = time.perf_counter()

        objects = [d for d in detections if d.class_id != "hand"]
        if allowed_ids is not None:
            objects = [d for d in objects if d.class_id in allowed_ids]
        objects.sort(key=lambda d: d.confidence, reverse=True)
        relations = hand_object_relations(hands, objects)

        return {
            "model": self.label,
            "width": width,
            "height": height,
            "latency_ms": {
                "decode": round((t1 - t0) * 1000, 1),
                "queue": round((t_start - t1) * 1000, 1),
                "detect": round((t2 - t_start) * 1000, 1),
                "hands": round((t3 - t2) * 1000, 1),
                "total": round((time.perf_counter() - t0) * 1000, 1),
            },
            "detections": [self._object_json(d) for d in objects],
            "hands": [
                {
                    "handedness": h.handedness,
                    "confidence": round(h.confidence, 3),
                    "box": _box_json(h.box),
                    "fingertips": [{"x": round(x, 4), "y": round(y, 4)} for x, y in h.fingertips],
                }
                for h in hands
            ],
            "relations": [vars(r) for r in relations],
        }

    def _object_json(self, d) -> dict:
        cls = self.vocab.by_id(d.class_id)
        x1, y1, x2, y2 = d.box
        return {
            "class_id": d.class_id,
            "label_en": cls.en,
            "label_el": cls.el,
            "group": cls.group,
            "hazard": cls.hazard,
            "confidence": round(d.confidence, 3),
            "box": _box_json(d.box),
            "center": {"x": round((x1 + x2) / 2, 4), "y": round((y1 + y2) / 2, 4)},
        }


def _box_json(box) -> dict:
    x1, y1, x2, y2 = (min(1.0, max(0.0, float(v))) for v in box)
    return {"x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4), "y2": round(y2, 4)}


_service: Optional[DetectionService] = None
_service_lock = threading.Lock()


def get_service() -> DetectionService:
    global _service
    if not detection_enabled():
        raise DetectionUnavailable("detection is disabled - set DETECTION_ENABLED=true")
    with _service_lock:
        if _service is None:
            _service = DetectionService(DetectionConfig.from_env())
        return _service


def reset_service() -> None:
    """For tests and config reloads."""
    global _service
    with _service_lock:
        _service = None
