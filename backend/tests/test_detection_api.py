"""/detect route tests. The real models are never loaded - a fake service stands in, so these
run without the optional requirements-detect.txt installed."""
import pytest
from fastapi.testclient import TestClient

from app import rate_limit, recipes
from app.detection import service as detection_service
from app.detection.vocab_match import fold, match_classes
from app.main import app

JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeService:
    def __init__(self):
        self.calls = []

    def run(self, jpeg, allowed_ids=None):
        self.calls.append((jpeg, allowed_ids))
        if jpeg == b"not-an-image":
            raise ValueError("body is not a decodable image")
        return {
            "model": "fake",
            "width": 640,
            "height": 480,
            "latency_ms": {"decode": 1.0, "detect": 2.0, "hands": 3.0, "total": 6.0},
            "detections": [{
                "class_id": "knife", "label_en": "knife", "label_el": "μαχαίρι", "group": "utensil",
                "hazard": True, "confidence": 0.9,
                "box": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.2}, "center": {"x": 0.2, "y": 0.15},
            }],
            "hands": [{
                "handedness": "Right", "confidence": 0.95,
                "box": {"x1": 0.2, "y1": 0.1, "x2": 0.4, "y2": 0.4}, "fingertips": [{"x": 0.25, "y": 0.15}],
            }],
            "relations": [{"hand": 0, "object": 0, "kind": "touching", "distance": 0.0}],
        }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    rate_limit._WINDOWS.clear()
    monkeypatch.delenv("BACKEND_PAIRING_TOKEN", raising=False)
    monkeypatch.delenv("DETECTION_ENABLED", raising=False)
    detection_service.reset_service()
    yield
    detection_service.reset_service()


@pytest.fixture
def fake(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(detection_service, "get_service", lambda: service)
    return service


def post(client, body, **params):
    return client.post("/detect", content=body, params=params, headers={"content-type": "image/jpeg"})


def test_returns_detections_hands_and_relations(client, fake):
    r = post(client, JPEG_BYTES)
    assert r.status_code == 200
    body = r.json()
    assert body["detections"][0]["class_id"] == "knife"
    assert body["relations"][0]["kind"] == "touching"
    assert fake.calls == [(JPEG_BYTES, None)]


def test_disabled_is_503_with_a_clear_message(client):
    r = post(client, JPEG_BYTES)
    assert r.status_code == 503
    assert "DETECTION_ENABLED" in r.json()["detail"]


def test_empty_body_is_400(client, fake):
    assert post(client, b"").status_code == 400
    assert fake.calls == []


def test_undecodable_image_is_400(client, fake):
    assert post(client, b"not-an-image").status_code == 400


def test_oversized_body_is_413(client, fake):
    assert post(client, b"x" * (3 * 1024 * 1024)).status_code == 413
    assert fake.calls == []


def test_chunked_oversized_body_is_413_without_content_length(client, fake):
    def chunks():
        for _ in range(3):
            yield b"x" * (1024 * 1024)

    r = client.post("/detect", content=chunks(), headers={"content-type": "image/jpeg"})
    assert r.status_code == 413
    assert fake.calls == []


def test_pairing_token_enforced_before_body_is_read(client, fake, monkeypatch):
    monkeypatch.setenv("BACKEND_PAIRING_TOKEN", "s3cret")
    assert post(client, JPEG_BYTES).status_code == 401
    ok = client.post("/detect", content=JPEG_BYTES, headers={"content-type": "image/jpeg", "X-Pairing-Token": "s3cret"})
    assert ok.status_code == 200
    assert len(fake.calls) == 1


def test_recipe_id_narrows_vocabulary(client, fake):
    post(client, JPEG_BYTES, recipe_id="scrambled_eggs")
    allowed = fake.calls[0][1]
    assert {"egg", "butter", "hand", "frying_pan"} <= allowed
    assert "banana" not in allowed


def test_unknown_recipe_means_no_narrowing(client, fake):
    post(client, JPEG_BYTES, recipe_id="does-not-exist")
    assert fake.calls[0][1] is None


class TestVocabMatch:
    def test_fold_strips_greek_tonos(self):
        assert fold("Κατσαρόλα") == "κατσαρολα"

    def test_plural_and_greek_case_endings_match(self):
        assert match_classes(["Crack the eggs"]) >= {"egg"}
        assert match_classes(["Βάζουμε την κατσαρόλα"]) >= {"pot"}
        assert match_classes(["στο μάτι της κουζίνας"]) >= {"stove"}

    def test_word_boundaries_prevent_prefix_hits(self):
        # "pan" must not fire on "pancakes"; "egg" must not fire on "eggplant".
        found = match_classes(["Serve the pancakes with eggplant"])
        assert "frying_pan" not in found
        assert "egg" not in found
        assert "pancake" in found

    def test_recipe_vocabulary_for_pasta(self):
        allowed = recipes.detection_vocabulary("pasta")
        assert {"pasta", "colander", "pot", "hand", "knife"} <= allowed
