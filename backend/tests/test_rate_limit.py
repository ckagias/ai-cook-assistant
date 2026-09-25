import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import barcode, rate_limit
from app.main import ANALYZE_RATE_LIMIT, BARCODE_RATE_LIMIT, app


def _make_jpeg_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(128, 128, 128)).save(buf, format="JPEG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


TINY_JPEG_B64 = _make_jpeg_b64()


@pytest.fixture(autouse=True)
def _clear_windows():
    rate_limit._WINDOWS.clear()
    yield
    rate_limit._WINDOWS.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for var in ("DEMO_MODE", "DEMO_STRICT", "VISION_PROVIDER", "BACKEND_PAIRING_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_STRICT", "true")
    # /barcode must never make a real call to Open Food Facts in a test.
    monkeypatch.setattr(barcode, "lookup_barcode", lambda code: _fake_barcode_lookup())


async def _fake_barcode_lookup():
    return {"product_name": "Test Product", "summary_for_speech": "Test Product."}


class TestCheckRateLimit:
    def test_requests_under_limit_succeed(self):
        for _ in range(3):
            assert rate_limit.check_rate_limit("k", max_requests=3, window_sec=60) is True

    def test_request_crossing_limit_rejected(self):
        for _ in range(3):
            assert rate_limit.check_rate_limit("k", max_requests=3, window_sec=60) is True
        assert rate_limit.check_rate_limit("k", max_requests=3, window_sec=60) is False

    def test_window_slides(self, monkeypatch):
        clock = {"t": 1000.0}
        monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock["t"])

        for _ in range(3):
            assert rate_limit.check_rate_limit("k", max_requests=3, window_sec=60) is True
        assert rate_limit.check_rate_limit("k", max_requests=3, window_sec=60) is False

        clock["t"] += 61  # past the window - the 3 old requests should drop out
        assert rate_limit.check_rate_limit("k", max_requests=3, window_sec=60) is True

    def test_different_keys_have_independent_windows(self):
        for _ in range(3):
            assert rate_limit.check_rate_limit("a", max_requests=3, window_sec=60) is True
        assert rate_limit.check_rate_limit("b", max_requests=3, window_sec=60) is True


class TestAnalyzeRateLimitIntegration:
    def test_requests_under_limit_succeed_then_429(self, client):
        max_requests, _ = ANALYZE_RATE_LIMIT
        for _ in range(max_requests):
            r = client.post(
                "/analyze", json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"}
            )
            assert r.status_code == 200
        r = client.post(
            "/analyze", json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"}
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers


class TestBarcodeRateLimitIntegration:
    def test_requests_under_limit_succeed_then_429(self, client):
        max_requests, _ = BARCODE_RATE_LIMIT
        for _ in range(max_requests):
            r = client.get("/barcode/0000000000000")
            assert r.status_code == 200
        r = client.get("/barcode/0000000000000")
        assert r.status_code == 429
        assert "Retry-After" in r.headers
