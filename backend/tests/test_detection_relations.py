from dataclasses import dataclass, field

from app.detection.relations import edge_distance, hand_object_relations


@dataclass
class H:
    box: tuple
    fingertips: list = field(default_factory=list)


@dataclass
class O:
    class_id: str
    box: tuple


HAND = H((0.40, 0.40, 0.50, 0.55), fingertips=[(0.45, 0.40)])


def kinds(hands, objects):
    return [(r.hand, r.object, r.kind) for r in hand_object_relations(hands, objects)]


def test_fingertip_on_small_object_is_touching():
    knife = O("knife", (0.43, 0.30, 0.60, 0.39))  # fingertip at y=0.40 is within the 2% margin
    assert kinds([HAND], [knife]) == [(0, 0, "touching")]


def test_heavy_box_overlap_is_touching_even_without_fingertips():
    bowl = O("bowl", (0.42, 0.45, 0.55, 0.60))
    assert kinds([H(HAND.box)], [bowl]) == [(0, 0, "touching")]


def test_hand_inside_large_surface_is_over_not_touching():
    stove = O("stove", (0.10, 0.10, 0.90, 0.90))
    assert kinds([HAND], [stove]) == [(0, 0, "over")]


def test_close_but_separate_is_near_with_distance():
    spoon = O("spoon", (0.55, 0.45, 0.60, 0.50))  # 0.05 to the right of the hand box
    rel = hand_object_relations([HAND], [spoon])
    assert [(r.kind, r.distance) for r in rel] == [("near", 0.05)]


def test_far_object_has_no_relation():
    pot = O("pot", (0.85, 0.85, 0.95, 0.95))
    assert kinds([HAND], [pot]) == []


def test_hand_detections_are_never_objects():
    assert kinds([HAND], [O("hand", HAND.box)]) == []


def test_sorted_touching_before_near_per_hand():
    spoon = O("spoon", (0.55, 0.45, 0.60, 0.50))
    knife = O("knife", (0.43, 0.30, 0.60, 0.39))
    assert [k for _, _, k in kinds([HAND], [spoon, knife])] == ["touching", "near"]


def test_edge_distance_zero_when_overlapping():
    assert edge_distance((0, 0, 0.5, 0.5), (0.4, 0.4, 0.9, 0.9)) == 0.0


def test_hybrid_hands_add_only_what_mediapipe_missed():
    from app.detection.hands import Hand, merge_hands

    landmarked = [Hand("Right", 0.9, (0.40, 0.40, 0.50, 0.55), fingertips=[(0.45, 0.4)])]
    detector = [((0.41, 0.41, 0.51, 0.56), 0.6), ((0.80, 0.70, 1.00, 1.00), 0.3)]  # same hand + an edge-of-frame one
    merged = merge_hands(landmarked, detector)
    assert len(merged) == 2
    assert merged[0].fingertips and merged[0].handedness == "Right"
    assert merged[1].box == (0.80, 0.70, 1.00, 1.00) and merged[1].fingertips == []



def test_one_object_boxed_as_two_classes_keeps_the_hazard():
    from app.detection.detector import Detection
    from app.detection.service import suppress_cross_class
    from app.detection.vocabulary import load_vocabulary

    scissors = Detection("scissors", 0.48, (0.10, 0.45, 0.97, 0.57))
    knife = Detection("knife", 0.40, (0.11, 0.45, 0.98, 0.58))
    bowl = Detection("bowl", 0.9, (0.1, 0.6, 0.3, 0.9))
    kept = suppress_cross_class([scissors, knife, bowl], load_vocabulary())
    assert [d.class_id for d in kept] == ["bowl", "knife"]  # best-first, knife beat the more confident scissors


def test_separate_objects_of_different_classes_are_both_kept():
    from app.detection.detector import Detection
    from app.detection.service import suppress_cross_class
    from app.detection.vocabulary import load_vocabulary

    a = Detection("spoon", 0.8, (0.1, 0.1, 0.2, 0.3))
    b = Detection("fork", 0.7, (0.5, 0.5, 0.6, 0.7))
    assert len(suppress_cross_class([a, b], load_vocabulary())) == 2
