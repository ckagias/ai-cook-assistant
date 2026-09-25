import json
import tempfile
from pathlib import Path
from app.importers import akis_petretzikis as ap
from app.importers.schema import StagedRecipe


def make_sample_next_data(id_):
    base = {
        "props": {
            "pageProps": {
                "ssRecipe": {
                    "data": {
                        "id": id_,
                        "title": {"el": "Τίτλος EL", "en": "Title EN"},
                        "method": [{"section": "", "steps": [{"id": 1, "step": "Step EL"}]}],
                        "ingredient_sections": [{"title": "", "ingredients": [{"title": "αλεύρι", "quantity": "100", "unit": "g", "info": ""}]}],
                        "make_time": 10,
                        "bake_time": None,
                        "shares": "2-3",
                        "difficulty": "Εύκολο",
                        "equipment_used": [{"title": "Τηγάνι"}],
                        "assets": [{"url": "https://example.com/img.jpg"}],
                        "video_url": "https://youtube.example",
                        "is_ve": 0,
                        "is_vg": 0,
                        "is_gf": 0,
                        "is_df": 0,
                        "is_ef": 0,
                        "is_nf": 0,
                    }
                }
            }
        }
    }
    return base


def test_normalize_and_stage_writes_manifest(tmp_path, monkeypatch):
    # Prepare staging dir under tmp_path
    monkeypatch.setattr(ap, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(ap, "MANIFEST_PATH", tmp_path / "staging" / "manifest.json")

    raw_el = make_sample_next_data("123")
    raw_en = make_sample_next_data("123")

    staged = ap.normalize(raw_el, raw_en)
    assert isinstance(staged, StagedRecipe)
    # Write staged
    ap.write_staged(staged, force_refetch=True)

    out_file = Path(ap.STAGING_ROOT) / "123.json"
    assert out_file.exists()
    manifest = json.loads(Path(ap.MANIFEST_PATH).read_text(encoding="utf-8"))
    assert any(e["source_id"] == "123" for e in manifest)
