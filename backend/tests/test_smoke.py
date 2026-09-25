import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import demo_cache, recipes, vision
from app.main import _apply_protein_safety, _apply_safety_flag, app
from app.schemas import AnalyzeResponse


def _make_jpeg_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(128, 128, 128)).save(buf, format="JPEG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


TINY_JPEG_B64 = _make_jpeg_b64()


def _full_response(**overrides) -> dict:
    base = dict(
        description="d",
        primary_subject="chicken",
        camera_feedback=None,
        doneness_stage="done",
        confidence="high",
        evidence=["pink", "raw"],
        alternate_guesses=[],
        needs_clarification=False,
        clarifying_question=None,
        raw_protein_detected=True,
        safety_flag=None,
        spoken_response="looks done",
    )
    base.update(overrides)
    return base


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    # No test may hit the network or a real API key - every provider path is exercised
    # through failure (missing credentials) or a monkeypatched stand-in.
    for var in (
        "DEMO_MODE",
        "DEMO_STRICT",
        "VISION_PROVIDER",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


# --- protein safety ---


class TestProteinSafety:
    def test_check_doneness_full_replace(self):
        resp = _full_response()
        out = _apply_protein_safety(resp, "check_doneness", "en", None)
        assert out["doneness_stage"] is None
        assert out["confidence"] == "low"
        assert out["evidence"] == []
        assert out["needs_clarification"] is False
        assert out["clarifying_question"] is None
        assert "thermometer" in out["spoken_response"].lower()

    def test_identify_appends_only(self):
        resp = _full_response()
        out = _apply_protein_safety(resp, "identify", "en", None)
        assert out["confidence"] == "high"
        assert "looks done" in out["spoken_response"]
        assert "thermometer" in out["spoken_response"].lower()

    def test_model_flagged_no_recipe_still_triggers(self):
        resp = _full_response(raw_protein_detected=True)
        out = _apply_protein_safety(resp, "check_doneness", "en", None)
        assert out["confidence"] == "low"

    def test_nothing_flagged_passes_through_unchanged(self):
        resp = _full_response(raw_protein_detected=False)
        out = _apply_protein_safety(resp, "check_doneness", "en", None)
        assert out == resp

    def test_recipe_false_beats_model_true(self):
        # The pancake-batter case: recipe curates contains_raw_protein=False even though
        # the model correctly flags raw egg, because "use a thermometer on a pancake" is
        # useless advice. This is the single most important test in the suite.
        resp = _full_response(raw_protein_detected=True)
        out = _apply_protein_safety(resp, "check_doneness", "en", False)
        assert out == resp

    def test_recipe_true_overrides_model_false(self):
        resp = _full_response(raw_protein_detected=False)
        out = _apply_protein_safety(resp, "check_doneness", "en", True)
        assert out["confidence"] == "low"

    @pytest.mark.parametrize(
        "recipe_id,step_index,expected",
        [
            ("pancakes", 2, False),
            ("scrambled_eggs", 1, True),
            ("scrambled_eggs", 0, True),
            (None, None, None),
            ("pasta", 99, None),
        ],
    )
    def test_step_contains_raw_protein_tri_state(self, recipe_id, step_index, expected):
        assert recipes.step_contains_raw_protein(recipe_id, step_index) is expected


# --- alarm/caution ---


class TestSafetyFlag:
    @pytest.mark.parametrize(
        "reason",
        [
            "steam rising off the pot",
            "haze near the pan",
            "vapor near the lid",
            "condensation on the window",
            "blackening visible but it is just steam",
        ],
    )
    def test_ambiguous_reasons_demote_to_caution(self, reason):
        resp = {"safety_flag": {"severity": "alarm", "reason": reason}}
        out = _apply_safety_flag(resp)
        assert out["safety_flag"]["severity"] == "caution"

    @pytest.mark.parametrize(
        "reason",
        [
            "visible flame on the stove",
            "the food is burning",
            "charred and blackened surface",
            "sparks near the burner",
        ],
    )
    def test_unambiguous_reasons_stay_alarm(self, reason):
        resp = {"safety_flag": {"severity": "alarm", "reason": reason}}
        out = _apply_safety_flag(resp)
        assert out["safety_flag"]["severity"] == "alarm"

    def test_caution_never_promoted_to_alarm(self):
        resp = {"safety_flag": {"severity": "caution", "reason": "flame visible"}}
        out = _apply_safety_flag(resp)
        assert out["safety_flag"]["severity"] == "caution"

    def test_missing_safety_flag_passes_through_as_none(self):
        resp = {"safety_flag": None}
        out = _apply_safety_flag(resp)
        assert out["safety_flag"] is None


# --- routes ---


class TestRoutes:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_recipes_list(self, client):
        r = client.get("/recipes")
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert ids == ["pasta", "pancakes", "scrambled_eggs"]

    def test_recipe_detail(self, client):
        r = client.get("/recipes/pasta")
        assert r.status_code == 200
        assert r.json()["id"] == "pasta"

    def test_recipe_404(self, client):
        r = client.get("/recipes/does-not-exist")
        assert r.status_code == 404

    def test_bad_base64_is_400_not_500(self, client):
        r = client.post("/analyze", json={"mode": "identify", "image_base64": "!!!not-base64!!!"})
        assert r.status_code == 400

    def test_static_mount_does_not_shadow_api(self, client):
        # /health is a real route registered before the static mount - must still resolve.
        r = client.get("/health")
        assert r.status_code == 200
        # probe.html is a real static file (Phase 15) - it must fall through to the
        # static handler and serve normally, not get swallowed by an API route.
        r2 = client.get("/probe.html")
        assert r2.status_code == 200
        assert "text/html" in r2.headers["content-type"]

    def test_reference_no_image_named_404(self, client):
        r = client.get("/reference/pasta/2")
        assert r.status_code == 404
        assert r.json()["detail"] == "no reference image for this step"

    def test_reference_named_but_missing_on_disk_404(self, client):
        r = client.get("/reference/pasta/0")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert "not on disk" in detail
        assert "pasta_boiling.jpg" in detail


# --- demo mode ---


class TestDemoMode:
    def test_fixture_cannot_bypass_recipe_safety_override(self, client, monkeypatch, tmp_path):
        # Proves DEMO_MODE cannot be used to skip a safety rule - the most important
        # demo-mode test in the suite.
        fixtures_dir = tmp_path / "demo_fixtures"
        fixtures_dir.mkdir()
        (fixtures_dir / "check_doneness__scrambled_eggs__1.json").write_text(
            json.dumps(_full_response(raw_protein_detected=False, confidence="high"))
        )
        monkeypatch.setattr(demo_cache, "FIXTURES_DIR", fixtures_dir)
        monkeypatch.setenv("DEMO_MODE", "true")

        r = client.post(
            "/analyze",
            json={
                "mode": "check_doneness",
                "image_base64": TINY_JPEG_B64,
                "language": "en",
                "recipe_id": "scrambled_eggs",
                "step_index": 1,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["confidence"] == "low"
        assert "thermometer" in body["spoken_response"].lower()

    def test_normal_fixture_serves_through(self, client, monkeypatch, tmp_path):
        fixtures_dir = tmp_path / "demo_fixtures"
        fixtures_dir.mkdir()
        (fixtures_dir / "check_doneness__pasta__1.json").write_text(
            json.dumps(
                _full_response(
                    raw_protein_detected=False, spoken_response="The pasta looks cooked through."
                )
            )
        )
        monkeypatch.setattr(demo_cache, "FIXTURES_DIR", fixtures_dir)
        monkeypatch.setenv("DEMO_MODE", "true")

        r = client.post(
            "/analyze",
            json={
                "mode": "check_doneness",
                "image_base64": TINY_JPEG_B64,
                "language": "en",
                "recipe_id": "pasta",
                "step_index": 1,
            },
        )
        assert r.status_code == 200
        assert r.json()["spoken_response"] == "The pasta looks cooked through."

    def test_demo_strict_canned_miss_never_hits_network(self, client, monkeypatch, tmp_path):
        fixtures_dir = tmp_path / "demo_fixtures"
        fixtures_dir.mkdir()
        monkeypatch.setattr(demo_cache, "FIXTURES_DIR", fixtures_dir)
        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("DEMO_STRICT", "true")

        r = client.post(
            "/analyze",
            json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"},
        )
        assert r.status_code == 200
        assert r.json()["confidence"] == "low"


# --- vision failure paths ---


class TestVisionFailurePaths:
    def test_exception_degrades_to_fallback(self, monkeypatch):
        monkeypatch.setenv("VISION_PROVIDER", "anthropic")

        def boom(image_bytes, ref_bytes, user_text):
            raise RuntimeError("boom")

        monkeypatch.setitem(vision._PROVIDER_CALLS, "anthropic", boom)
        result = vision.analyze_frame(b"img", {"mode": "identify", "language": "en"})
        AnalyzeResponse.model_validate(result)
        assert result["confidence"] == "low"

    def test_none_parsed_degrades_to_fallback(self, monkeypatch):
        monkeypatch.setenv("VISION_PROVIDER", "anthropic")
        monkeypatch.setitem(vision._PROVIDER_CALLS, "anthropic", lambda *a, **k: None)
        result = vision.analyze_frame(b"img", {"mode": "identify", "language": "en"})
        AnalyzeResponse.model_validate(result)
        assert result["confidence"] == "low"

    def test_unknown_provider_degrades_to_fallback(self, monkeypatch):
        monkeypatch.setenv("VISION_PROVIDER", "not-a-real-provider")
        result = vision.analyze_frame(b"img", {"mode": "identify", "language": "en"})
        AnalyzeResponse.model_validate(result)
        assert result["confidence"] == "low"

    def test_never_returns_500_via_http(self, client, monkeypatch):
        monkeypatch.setenv("VISION_PROVIDER", "anthropic")
        r = client.post(
            "/analyze", json={"mode": "identify", "image_base64": TINY_JPEG_B64, "language": "en"}
        )
        assert r.status_code == 200
        assert r.json()["confidence"] == "low"


# --- provider seam ---


class TestProviderSeam:
    @pytest.mark.parametrize("provider", ["anthropic", "openai", "gemini"])
    def test_env_var_selects_correct_function(self, monkeypatch, provider):
        monkeypatch.setenv("VISION_PROVIDER", provider)
        called = {}

        def spy(image_bytes, ref_bytes, user_text):
            called["provider"] = provider
            return AnalyzeResponse(
                description="d", primary_subject="p", confidence="high", spoken_response="ok"
            )

        monkeypatch.setitem(vision._PROVIDER_CALLS, provider, spy)
        result = vision.analyze_frame(b"img", {"mode": "identify", "language": "en"})
        assert called.get("provider") == provider
        assert result["spoken_response"] == "ok"

    def test_anthropic_schema_normalizer_accepts_analyze_response(self):
        import anthropic.lib._parse._transform as transform

        schema = transform.transform_schema(AnalyzeResponse)
        assert schema

    def test_openai_schema_normalizer_accepts_analyze_response(self):
        import openai.lib._pydantic as pydantic_lib

        schema = pydantic_lib.to_strict_json_schema(AnalyzeResponse)
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"].keys())

    def test_gemini_schema_normalizer_accepts_analyze_response(self):
        import google.genai._transformers as transformers

        schema = transformers.t_schema(None, AnalyzeResponse)
        assert schema.properties["camera_feedback"].nullable is True
        # Gemini only marks a field required if it has no Python default - documenting
        # the asymmetry, not fighting it. The recipe-driven trigger in main.py is
        # unaffected since it never depends on this field being present.
        assert "raw_protein_detected" not in schema.required
        for field in ("description", "confidence", "spoken_response"):
            assert field in schema.required


# --- reference image resolution ---


class TestReferenceImageResolution:
    def test_none_for_step_with_no_reference(self):
        assert vision._reference_image_bytes({"recipe_id": "pasta", "step_index": 2}) is None

    def test_none_for_no_recipe_or_step(self):
        assert vision._reference_image_bytes({"recipe_id": None, "step_index": None}) is None

    def test_real_call_passes_resolved_bytes_and_prompt_contains_mode(self, monkeypatch, tmp_path):
        ref_dir = tmp_path / "data" / "reference_images"
        ref_dir.mkdir(parents=True)
        (ref_dir / "pancake_ready_to_flip.jpg").write_bytes(base64.standard_b64decode(TINY_JPEG_B64))
        monkeypatch.setattr(vision, "BACKEND_ROOT", tmp_path)
        monkeypatch.setenv("VISION_PROVIDER", "anthropic")

        captured = {}

        def spy(image_bytes, ref_bytes, user_text):
            captured["ref_bytes"] = ref_bytes
            captured["user_text"] = user_text
            return AnalyzeResponse(
                description="d", primary_subject="p", confidence="high", spoken_response="ok"
            )

        monkeypatch.setitem(vision._PROVIDER_CALLS, "anthropic", spy)
        vision.analyze_frame(
            base64.standard_b64decode(TINY_JPEG_B64),
            {"mode": "check_doneness", "language": "en", "recipe_id": "pancakes", "step_index": 2},
        )
        assert captured["ref_bytes"] is not None
        assert "Mode: check_doneness" in captured["user_text"]
