import base64
import io

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image
from starlette.requests import Request

from app import main as main_module
from app import rate_limit, vision
from app.main import MAX_ANALYZE_CONTENT_LENGTH, MAX_DECODED_IMAGE_BYTES, app


def _make_jpeg_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(128, 128, 128)).save(buf, format="JPEG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


TINY_JPEG_B64 = _make_jpeg_b64()


@pytest.fixture(autouse=True)
def _clear_windows():
    rate_limit._WINDOWS.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for var in ("DEMO_MODE", "DEMO_STRICT", "VISION_PROVIDER", "BACKEND_PAIRING_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("VISION_PROVIDER", "anthropic")


class TestContentLengthMiddleware:
    async def _call_middleware(self, content_length: int | None):
        headers = [] if content_length is None else [(b"content-length", str(content_length).encode())]
        scope = {"type": "http", "method": "POST", "path": "/analyze", "headers": headers}
        request = Request(scope)
        called = {"count": 0}

        async def call_next(_req):
            called["count"] += 1
            return JSONResponse({"ok": True})

        response = await main_module._limit_analyze_content_length(request, call_next)
        return response, called["count"]

    @pytest.mark.anyio
    async def test_oversized_content_length_rejected_before_call_next(self):
        response, call_count = await self._call_middleware(MAX_ANALYZE_CONTENT_LENGTH + 1)
        assert response.status_code == 413
        assert call_count == 0

    @pytest.mark.anyio
    async def test_content_length_under_ceiling_passes_through(self):
        response, call_count = await self._call_middleware(1024)
        assert response.status_code == 200
        assert call_count == 1

    @pytest.mark.anyio
    async def test_missing_content_length_passes_through(self):
        response, call_count = await self._call_middleware(None)
        assert response.status_code == 200
        assert call_count == 1

    @pytest.mark.anyio
    async def test_other_paths_are_not_checked(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/recipes",
            "headers": [(b"content-length", str(MAX_ANALYZE_CONTENT_LENGTH + 1).encode())],
        }
        request = Request(scope)
        called = {"count": 0}

        async def call_next(_req):
            called["count"] += 1
            return JSONResponse({"ok": True})

        response = await main_module._limit_analyze_content_length(request, call_next)
        assert response.status_code == 200
        assert called["count"] == 1


class TestPostDecodeSizeCap:
    def test_request_under_both_limits_proceeds_normally(self, client, monkeypatch):
        monkeypatch.setitem(
            vision._PROVIDER_CALLS,
            "anthropic",
            lambda *a, **k: vision.AnalyzeResponse(
                description="d", primary_subject="p", confidence="high", spoken_response="ok"
            ),
        )
        r = client.post(
            "/analyze", json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"}
        )
        assert r.status_code == 200

    def test_oversized_decoded_image_rejected_before_vision_call(self, client, monkeypatch):
        called = {"count": 0}

        def spy(*a, **k):
            called["count"] += 1
            raise AssertionError("vision.analyze_frame must never be called for an oversized payload")

        monkeypatch.setitem(vision._PROVIDER_CALLS, "anthropic", spy)

        oversized_raw = b"x" * (MAX_DECODED_IMAGE_BYTES + 1)
        oversized_b64 = base64.standard_b64encode(oversized_raw).decode("ascii")
        assert len(oversized_b64) < MAX_ANALYZE_CONTENT_LENGTH  # confirms it clears the Content-Length gate

        r = client.post(
            "/analyze", json={"mode": "identify", "image_base64": oversized_b64, "language": "en"}
        )
        assert r.status_code == 413
        assert called["count"] == 0
