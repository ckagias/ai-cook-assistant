import pytest

from app.detection.metrics import (
    GroundTruth,
    ImageSample,
    Prediction,
    average_precision,
    evaluate,
    ioa,
    iou,
    weighted_mean_ap,
)
from app.detection.vocabulary import load_vocabulary

A = (0.1, 0.1, 0.3, 0.3)
B = (0.6, 0.6, 0.9, 0.9)


class TestGeometry:
    def test_iou_identical_and_disjoint(self):
        assert iou(A, A) == pytest.approx(1.0)
        assert iou(A, B) == 0.0

    def test_iou_half_overlap(self):
        # Two 0.2x0.2 boxes offset by half a width: intersection 0.02, union 0.06.
        assert iou((0.0, 0.0, 0.2, 0.2), (0.1, 0.0, 0.3, 0.2)) == pytest.approx(1 / 3)

    def test_ioa_small_box_inside_big(self):
        assert ioa((0.2, 0.2, 0.3, 0.3), (0.0, 0.0, 1.0, 1.0)) == pytest.approx(1.0)


class TestAveragePrecision:
    def test_perfect_ranking(self):
        assert average_precision([(0.9, True), (0.8, True)], 2) == pytest.approx(1.0)

    def test_false_positive_ranked_first_halves_early_precision(self):
        # FP, TP, TP over 2 GT: precision envelope is 2/3 across the whole recall range.
        assert average_precision([(0.9, False), (0.8, True), (0.7, True)], 2) == pytest.approx(2 / 3)

    def test_no_ground_truth_is_zero(self):
        assert average_precision([(0.9, False)], 0) == 0.0


class TestEvaluate:
    def test_tp_fp_and_miss(self):
        samples = {"img": ImageSample([GroundTruth("knife", A), GroundTruth("knife", B)])}
        preds = {"img": [Prediction("knife", A, 0.9), Prediction("knife", (0.4, 0.4, 0.5, 0.5), 0.8)]}
        score = evaluate(samples, preds)["knife"]
        assert (score.n_gt, score.tp, score.fp) == (2, 1, 1)
        assert score.recall == pytest.approx(0.5)
        assert score.precision == pytest.approx(0.5)

    def test_unverified_class_detection_is_not_a_false_positive(self):
        # Open Images protocol: nobody verified "spoon" for this image, so a spoon detection is ignored.
        samples = {"img": ImageSample([GroundTruth("knife", A)], evaluable={"knife"})}
        preds = {"img": [Prediction("knife", A, 0.9), Prediction("spoon", B, 0.9)]}
        scores = evaluate(samples, preds)
        assert "spoon" not in scores
        assert scores["knife"].fp == 0

    def test_verified_absent_class_detection_is_a_false_positive(self):
        samples = {
            "img": ImageSample([GroundTruth("knife", A)], evaluable={"knife", "spoon"}),
            "img2": ImageSample([GroundTruth("spoon", B)]),
        }
        preds = {"img": [Prediction("spoon", B, 0.9)]}
        assert evaluate(samples, preds)["spoon"].fp == 1

    def test_group_of_box_credits_one_hit_and_ignores_the_rest(self):
        pile = (0.0, 0.0, 0.5, 0.5)
        samples = {"img": ImageSample([GroundTruth("tomato", pile, group_of=True)])}
        preds = {"img": [
            Prediction("tomato", (0.0, 0.0, 0.1, 0.1), 0.9),
            Prediction("tomato", (0.2, 0.2, 0.3, 0.3), 0.8),
        ]}
        score = evaluate(samples, preds)["tomato"]
        assert (score.n_gt, score.tp, score.fp) == (1, 1, 0)

    def test_confidence_threshold_affects_operating_point_not_ap(self):
        samples = {"img": ImageSample([GroundTruth("egg", A)])}
        preds = {"img": [Prediction("egg", A, 0.1)]}
        score = evaluate(samples, preds, conf_thr=0.25)["egg"]
        assert score.recall == 0.0
        assert score.ap50 == pytest.approx(1.0)

    def test_weighted_mean(self):
        samples = {"i": ImageSample([GroundTruth("hand", A), GroundTruth("egg", B)])}
        preds = {"i": [Prediction("hand", A, 0.9)]}
        scores = evaluate(samples, preds)
        assert weighted_mean_ap(scores, {"hand": 3.0, "egg": 1.0}) == pytest.approx(0.75)


class TestVocabulary:
    def test_loads_and_indexes(self):
        vocab = load_vocabulary()
        assert vocab.by_id("hand").group == "hand"
        assert vocab.oiv7_to_id()["Kitchen knife"] == "knife"
        assert vocab.prompt_to_id()["wok"] == "frying_pan"
        assert "hand" in vocab.base_ids()
        assert len(vocab.prompt_list()) == len(set(vocab.prompt_list()))

    def test_rejects_an_open_images_name_mapped_twice(self):
        from app.detection.vocabulary import Vocabulary

        with pytest.raises(ValueError, match="mapped twice"):
            Vocabulary.model_validate({
                "version": 1,
                "groups": ["utensil"],
                "classes": [
                    {"id": "a", "group": "utensil", "en": "a", "el": "a", "prompts": ["a"], "oiv7": ["Knife"]},
                    {"id": "b", "group": "utensil", "en": "b", "el": "b", "prompts": ["b"], "oiv7": ["Knife"]},
                ],
            })
