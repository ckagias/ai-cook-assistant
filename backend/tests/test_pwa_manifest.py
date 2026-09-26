"""PWA manifest is served with the right type, and its icon files exist on disk."""
import importlib.util
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from app.main import STATIC_DIR, app

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _generate_icons():
    spec = importlib.util.spec_from_file_location("generate_pwa_icons", SCRIPTS / "generate_pwa_icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate(STATIC_DIR / "icons")


def test_generate_pwa_icons_writes_expected_sizes(tmp_path):
    spec = importlib.util.spec_from_file_location("generate_pwa_icons", SCRIPTS / "generate_pwa_icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = {p.name: p for p in module.generate(tmp_path)}
    assert Image.open(paths["icon-192.png"]).size == (192, 192)
    assert Image.open(paths["icon-512.png"]).size == (512, 512)
    assert Image.open(paths["icon-512-maskable.png"]).size == (512, 512)


def test_manifest_is_json_and_icons_exist_on_disk():
    _generate_icons()
    client = TestClient(app)
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    data = r.json()
    assert data["display"] == "standalone"
    assert data["start_url"] == "/"
    assert "orientation" not in data
    assert data["background_color"] == "#111111"
    assert len(data["icons"]) == 3
    for icon in data["icons"]:
        path = STATIC_DIR / icon["src"].lstrip("/")
        assert path.is_file(), f"missing {path}"
