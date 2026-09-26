"""Detection scoring for the model benchmark. Pure functions, no ML dependency.

Follows the Open Images evaluation protocol in the two places it matters for a fair score
on a non-exhaustively labeled dataset:

- A detection only counts against precision for classes a human verified for that image
  (present or absent). A spoon in an Open Images photo nobody asked about is not a false
  positive, just unlabeled.
- A "group-of" box (e.g. a pile of tomatoes) counts as one ground truth; the first
  detection inside it is a true positive and further detections inside it are ignored.

Boxes are (x1, y1, x2, y2), normalized to 0-1.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]


@dataclass
class GroundTruth:
    class_id: str
    box: Box
    group_of: bool = False


@dataclass
class Prediction:
    class_id: str
    box: Box
    confidence: float


@dataclass
class ClassScore:
    class_id: str
    n_gt: int = 0
    ap50: float = 0.0
    precision: float = 0.0  # at the operating confidence threshold
    recall: float = 0.0
    tp: int = 0
    fp: int = 0


@dataclass
class ImageSample:
    ground_truth: list[GroundTruth]
    # Classes whose presence/absence was verified for this image. For an exhaustively
    # labeled in-house set, pass every vocabulary id.
    evaluable: set[str] = field(default_factory=set)


def area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def intersection(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def iou(a: Box, b: Box) -> float:
    inter = intersection(a, b)
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def ioa(inner: Box, outer: Box) -> float:
    """Fraction of `inner` covered by `outer` - how Open Images matches group-of boxes."""
    a = area(inner)
    return intersection(inner, outer) / a if a > 0 else 0.0


def _match_image(gts: list[GroundTruth], preds: list[Prediction], iou_thr: float) -> list[tuple[Prediction, bool]]:
    """Greedy per-class matching, highest confidence first. Returns (prediction, is_tp) for every
    prediction that counts; ignored ones (extra hits inside a group-of box) are dropped."""
    out: list[tuple[Prediction, bool]] = []
    singles = [g for g in gts if not g.group_of]
    groups = [g for g in gts if g.group_of]
    single_used = [False] * len(singles)
    group_used = [False] * len(groups)

    for pred in sorted(preds, key=lambda p: p.confidence, reverse=True):
        best, best_iou = -1, iou_thr
        for i, gt in enumerate(singles):
            if single_used[i]:
                continue
            overlap = iou(pred.box, gt.box)
            if overlap >= best_iou:
                best, best_iou = i, overlap
        if best >= 0:
            single_used[best] = True
            out.append((pred, True))
            continue

        hit_group = next((i for i, gt in enumerate(groups) if ioa(pred.box, gt.box) >= iou_thr), None)
        if hit_group is not None:
            if not group_used[hit_group]:
                group_used[hit_group] = True
                out.append((pred, True))
            # else: ignored - a second detection inside an already-credited group box
            continue

        out.append((pred, False))
    return out


def average_precision(flags: list[tuple[float, bool]], n_gt: int) -> float:
    """VOC-style all-point interpolated AP from (confidence, is_tp) pairs pooled across images."""
    if n_gt == 0:
        return 0.0
    ordered = sorted(flags, key=lambda f: f[0], reverse=True)
    tp = fp = 0
    precisions: list[float] = []
    recalls: list[float] = []
    for _, is_tp in ordered:
        if is_tp:
            tp += 1
        else:
            fp += 1
        precisions.append(tp / (tp + fp))
        recalls.append(tp / n_gt)
    # Precision envelope: make precision monotonically non-increasing from the right.
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])
    ap, prev_recall = 0.0, 0.0
    for p, r in zip(precisions, recalls):
        ap += (r - prev_recall) * p
        prev_recall = r
    return ap


def evaluate(
    samples: dict[str, ImageSample],
    predictions: dict[str, list[Prediction]],
    *,
    iou_thr: float = 0.5,
    conf_thr: float = 0.25,
) -> dict[str, ClassScore]:
    """Per-class AP50 plus precision/recall at `conf_thr`. Only classes with at least one
    ground-truth box appear in the result - a class nobody labeled can't be scored."""
    flags: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    n_gt: dict[str, int] = defaultdict(int)

    for image_id, sample in samples.items():
        gts_by_class: dict[str, list[GroundTruth]] = defaultdict(list)
        for gt in sample.ground_truth:
            gts_by_class[gt.class_id].append(gt)
            n_gt[gt.class_id] += 1
        evaluable = sample.evaluable | set(gts_by_class)

        preds_by_class: dict[str, list[Prediction]] = defaultdict(list)
        for pred in predictions.get(image_id, []):
            if pred.class_id in evaluable:
                preds_by_class[pred.class_id].append(pred)

        for class_id, preds in preds_by_class.items():
            for pred, is_tp in _match_image(gts_by_class.get(class_id, []), preds, iou_thr):
                flags[class_id].append((pred.confidence, is_tp))

    scores: dict[str, ClassScore] = {}
    for class_id, total in n_gt.items():
        class_flags = flags.get(class_id, [])
        above = [is_tp for conf, is_tp in class_flags if conf >= conf_thr]
        tp = sum(above)
        fp = len(above) - tp
        scores[class_id] = ClassScore(
            class_id=class_id,
            n_gt=total,
            ap50=average_precision(class_flags, total),
            precision=tp / (tp + fp) if (tp + fp) else 0.0,
            recall=tp / total,
            tp=tp,
            fp=fp,
        )
    return scores


def weighted_mean_ap(scores: dict[str, ClassScore], class_weights: dict[str, float]) -> float:
    """Mean AP50 over scored classes, each weighted (e.g. by its group's importance)."""
    total_w = sum(class_weights.get(c, 1.0) for c in scores)
    if total_w == 0:
        return 0.0
    return sum(s.ap50 * class_weights.get(c, 1.0) for c, s in scores.items()) / total_w
