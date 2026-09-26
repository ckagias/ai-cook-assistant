"""Where the hands are relative to detected objects. Pure geometry, no ML dependency.

The camera sees a 2D projection with no depth, so "touching" really means "overlapping in
the image". That's why there is a separate "over" relation: a hand inside the box of a much
larger object (a stove, a cutting board) is above it, and the image can't say whether it is
in contact. Never present any of these as a safety guarantee.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from .metrics import Box, area, intersection

TOUCH_MARGIN = 0.02  # fingertip within 2% of the frame of an object's box counts as on it
TOUCH_OVERLAP = 0.25  # or: hand/object boxes overlap by >= 25% of the smaller one
LARGE_OBJECT_RATIO = 4.0  # an object this many times the hand's area is a surface, not a thing held
OVER_FRACTION = 0.5  # at least half the hand box inside such an object -> "over"
NEAR_FACTOR = 0.5  # edge-to-edge gap <= half the hand-box diagonal -> "near"


class HasBox(Protocol):
    box: Box


class HandLike(HasBox, Protocol):
    fingertips: list[tuple[float, float]]


class ObjectLike(HasBox, Protocol):
    class_id: str


@dataclass
class Relation:
    hand: int  # index into the hands list
    object: int  # index into the detections list
    kind: str  # "touching" | "over" | "near"
    distance: float  # normalized edge-to-edge gap, 0 when the boxes overlap


def expand(box: Box, margin: float) -> Box:
    return (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)


def point_in_box(point: tuple[float, float], box: Box) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def edge_distance(a: Box, b: Box) -> float:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def classify(hand: HandLike, obj: HasBox) -> tuple[str, float] | None:
    hand_area, obj_area = area(hand.box), area(obj.box)
    if hand_area <= 0 or obj_area <= 0:
        return None
    inter = intersection(hand.box, obj.box)
    gap = edge_distance(hand.box, obj.box)

    if obj_area >= LARGE_OBJECT_RATIO * hand_area and inter / hand_area >= OVER_FRACTION:
        return "over", 0.0

    target = expand(obj.box, TOUCH_MARGIN)
    if any(point_in_box(tip, target) for tip in hand.fingertips) or inter / min(hand_area, obj_area) >= TOUCH_OVERLAP:
        return "touching", gap

    diagonal = math.hypot(hand.box[2] - hand.box[0], hand.box[3] - hand.box[1])
    if gap <= NEAR_FACTOR * diagonal:
        return "near", gap
    return None


_KIND_ORDER = {"touching": 0, "over": 1, "near": 2}


def hand_object_relations(hands: Sequence[HandLike], objects: Sequence[ObjectLike]) -> list[Relation]:
    relations = []
    for hi, hand in enumerate(hands):
        for oi, obj in enumerate(objects):
            if obj.class_id == "hand":
                continue
            result = classify(hand, obj)
            if result is not None:
                relations.append(Relation(hi, oi, result[0], round(result[1], 4)))
    relations.sort(key=lambda r: (r.hand, _KIND_ORDER[r.kind], r.distance))
    return relations
