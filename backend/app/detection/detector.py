"""Object detector backends behind one interface. The benchmark script and the /detect
service load models through the same code, so what gets measured is what gets served.

Two pretrained families, neither trained or fine-tuned here:

- "oiv7": yolov8{n,s,m,l,x}-oiv7 - closed vocabulary (601 Open Images classes, including
  Human hand). "Cut down" = keep only the classes our vocabulary maps, via predict(classes=...).
- "yoloe": yoloe-26{s,m,l}-seg - open vocabulary. "Cut down" = set_classes(our prompts);
  export bakes that vocabulary into the weights so the ~254 MB text encoder is only needed
  once, at export time. Masks are produced but ignored - we only use boxes.

Needs the optional requirements-detect.txt; import this module lazily.
"""
from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .metrics import iou

if TYPE_CHECKING:  # numpy arrives with ultralytics; keep this module importable without it
    import numpy as np
from .vocabulary import Vocabulary, load_vocabulary

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
EXPORT_DIR = MODELS_DIR / "exported"
FORMATS = ("torch", "onnx", "openvino")
# Two model classes/prompts mapping onto one vocabulary id (Knife + Kitchen knife, "frying pan"
# + "wok") would otherwise report the same object twice.
MERGE_IOU = 0.6


@dataclass
class Detection:
    class_id: str
    confidence: float
    box: tuple[float, float, float, float]  # normalized x1, y1, x2, y2


def family(model_name: str) -> str:
    if model_name.startswith("yoloe"):
        return "yoloe"
    if model_name.endswith("-oiv7"):
        return "oiv7"
    raise ValueError(f"unsupported detector model: {model_name!r} (expected yolov8*-oiv7 or yoloe-*)")


def disable_ultralytics_telemetry() -> None:
    # Ultralytics sends anonymous usage analytics by default; a kitchen camera app shouldn't.
    from ultralytics import settings

    if settings.get("sync"):
        settings.update({"sync": False})


def merge_duplicates(dets: list[Detection], iou_thr: float = MERGE_IOU) -> list[Detection]:
    kept: list[Detection] = []
    for det in sorted(dets, key=lambda d: d.confidence, reverse=True):
        if any(k.class_id == det.class_id and iou(k.box, det.box) >= iou_thr for k in kept):
            continue
        kept.append(det)
    return kept


class UltralyticsDetector:
    """One loaded model plus the mapping from its class indices onto vocabulary ids."""

    def __init__(self, label: str, model, index_to_id: dict[int, str], imgsz: int, filter_classes: bool,
                 rect: bool = False):
        self.label = label
        self.model = model
        self.index_to_id = index_to_id
        self.imgsz = imgsz
        # rect: letterbox to the frame's own shape (a 16:9 frame -> 480x288) instead of a padded
        # square (480x480) - same resolution, ~40% less work. Needs a dynamic-shape export.
        self.rect = rect
        # Only the closed-vocabulary model needs filtering; a YOLOE model only knows our prompts.
        self._classes = sorted(index_to_id) if filter_classes else None

    def detect(self, image_bgr: np.ndarray, conf: float) -> list[Detection]:
        h, w = image_bgr.shape[:2]
        result = self.model.predict(
            image_bgr, imgsz=self.imgsz, conf=conf, classes=self._classes, rect=self.rect, verbose=False
        )[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        dets = []
        for (x1, y1, x2, y2), score, idx in zip(xyxy, confs, classes):
            class_id = self.index_to_id.get(int(idx))
            if class_id is None:
                continue
            box = (float(x1) / w, float(y1) / h, float(x2) / w, float(y2) / h)  # plain floats: JSON-safe
            dets.append(Detection(class_id, float(score), box))
        return merge_duplicates(dets)


def weights_path(model_name: str) -> Path:
    return MODELS_DIR / f"{model_name}.pt"


def exported_path(model_name: str, imgsz: int, fmt: str, vocab: Vocabulary, dynamic: bool = False) -> Path:
    stem = f"{model_name}_{imgsz}"
    if family(model_name) == "yoloe":
        stem += f"_{vocab.fingerprint()}"  # the vocabulary is baked in - a new list needs a new export
    if dynamic:
        stem += "_dyn"
    return EXPORT_DIR / (f"{stem}.onnx" if fmt == "onnx" else f"{stem}_openvino_model")


def _index_to_id(names, model_name: str, vocab: Vocabulary) -> dict[int, str]:
    names = dict(names) if isinstance(names, dict) else dict(enumerate(names))
    lookup = vocab.oiv7_to_id() if family(model_name) == "oiv7" else vocab.prompt_to_id()
    return {int(i): lookup[n] for i, n in names.items() if n in lookup}


@contextmanager
def _working_dir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _load_torch(model_name: str, vocab: Vocabulary):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = str(weights_path(model_name))  # ultralytics downloads the release asset to this exact path
    if family(model_name) == "yoloe":
        from ultralytics import YOLOE

        model = YOLOE(path)
        # set_classes fetches the ~254 MB text encoder by bare file name into the *current*
        # directory; pin that to models/ (load-time only, never on a request path).
        with _working_dir(MODELS_DIR):
            model.set_classes(vocab.prompt_list())
        return model
    from ultralytics import YOLO

    return YOLO(path)


def export(model_name: str, imgsz: int, fmt: str, vocab: Optional[Vocabulary] = None, dynamic: bool = False) -> Path:
    """Export once to ONNX / OpenVINO (FP32); cached by file name. dynamic: any input shape up
    to imgsz on the long side, so frames can be letterboxed to their own aspect ratio."""
    vocab = vocab or load_vocabulary()
    target = exported_path(model_name, imgsz, fmt, vocab, dynamic)
    if target.exists():
        return target
    model = _load_torch(model_name, vocab)
    produced = Path(model.export(format=fmt, imgsz=imgsz, dynamic=dynamic, verbose=False))
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), str(target))
    return target


def load_detector(model_name: str, imgsz: int = 640, fmt: str = "torch", vocab: Optional[Vocabulary] = None,
                  rect: bool = False) -> UltralyticsDetector:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}, expected one of {FORMATS}")
    disable_ultralytics_telemetry()
    vocab = vocab or load_vocabulary()
    fam = family(model_name)

    if fmt == "torch":
        model = _load_torch(model_name, vocab)
    else:
        from ultralytics import YOLO

        model = YOLO(str(export(model_name, imgsz, fmt, vocab, dynamic=rect)), task="segment" if fam == "yoloe" else "detect")

    mapping = _index_to_id(model.names, model_name, vocab)
    if not mapping:
        raise RuntimeError(f"{model_name}: none of the model's classes map onto the vocabulary")
    label = f"{model_name}@{imgsz}{'r' if rect else ''}/{fmt}"
    return UltralyticsDetector(label, model, mapping, imgsz, filter_classes=fam == "oiv7", rect=rect)
