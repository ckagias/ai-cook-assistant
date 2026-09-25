import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import auth, barcode
from app.main import app


def _make_jpeg_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(128, 128, 128)).save(buf, format="JPEG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


TINY_JPEG_B64 = _make_jpeg_b64()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for var in ("DEMO_MODE", "DEMO_STRICT", "VISION_PROVIDER", "BACKEND_PAIRING_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    # /analyze needs a real fixture miss to stay hermetic and never hit the network.
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_STRICT", "true")
    # /barcode must never make a real call to Open Food Facts in a test.
    monkeypatch.setattr(barcode, "lookup_barcode", lambda code: _fake_barcode_lookup())


async def _fake_barcode_lookup():
    return {"product_name": "Test Product", "summary_for_speech": "Test Product."}


PROTECTED_GET_ROUTES = ["/recipes", "/recipes/pasta", "/barcode/0000000000000", "/reference/pasta/0"]


class TestPairingTokenDisabled:
    def test_analyze_works_with_no_header(self, client):
        r = client.post(
            "/analyze", json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"}
        )
        assert r.status_code == 200

    @pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
    def test_protected_routes_work_with_no_header(self, client, path):
        r = client.get(path)
        assert r.status_code == 200

    def test_health_works_with_no_header(self, client):
        r = client.get("/health")
        assert r.status_code == 200


class TestPairingTokenEnabled:
    @pytest.fixture(autouse=True)
    def _enable_token(self, monkeypatch):
        monkeypatch.setenv("BACKEND_PAIRING_TOKEN", "s3cret")

    def test_analyze_missing_header_401(self, client):
        r = client.post(
            "/analyze", json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"}
        )
        assert r.status_code == 401

    def test_analyze_wrong_header_401(self, client):
        r = client.post(
            "/analyze",
            json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"},
            headers={"X-Pairing-Token": "wrong"},
        )
        assert r.status_code == 401

    def test_analyze_correct_header_succeeds(self, client):
        r = client.post(
            "/analyze",
            json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"},
            headers={"X-Pairing-Token": "s3cret"},
        )
        assert r.status_code == 200

    @pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
    def test_protected_routes_missing_header_401(self, client, path):
        r = client.get(path)
        assert r.status_code == 401

    @pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
    def test_protected_routes_correct_header_not_401(self, client, path):
        r = client.get(path, headers={"X-Pairing-Token": "s3cret"})
        assert r.status_code != 401

    def test_health_still_works_with_no_header(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_static_mount_still_works_with_no_header(self, client):
        r = client.get("/probe.html")
        assert r.status_code == 200


class TestPairingTokenEnabledFlag:
    def test_disabled_when_unset(self, monkeypatch):
        monkeypatch.delenv("BACKEND_PAIRING_TOKEN", raising=False)
        assert auth.pairing_token_enabled() is False

    def test_enabled_when_set(self, monkeypatch):
        monkeypatch.setenv("BACKEND_PAIRING_TOKEN", "x")
        assert auth.pairing_token_enabled() is True
