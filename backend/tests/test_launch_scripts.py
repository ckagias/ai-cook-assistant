"""start.* helpers: the setup stamp that lets a start skip setup, and the app window's
pre-allowed camera."""
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_backend(tmp_path):
    backend = tmp_path / "backend"
    (backend / "app" / "detection").mkdir(parents=True)
    (backend / "models").mkdir()
    (backend / "requirements.txt").write_text("fastapi>=0.115\n")
    (backend / "requirements-detect.txt").write_text("ultralytics==8.4.163\n")
    (backend / "app" / "detection" / "vocabulary.json").write_text("[]")
    (backend / ".env").write_text("DETECTOR_MODEL=yoloe-26s-seg\nOPENAI_API_KEY=x\n")
    (backend / "models" / "hand_landmarker.task").write_bytes(b"x")
    return backend


def test_stamp_skips_setup_until_something_changes(tmp_path, monkeypatch):
    stamp = _load("setup_stamp")
    backend = _fake_backend(tmp_path)
    monkeypatch.setattr(stamp, "BACKEND_DIR", backend)
    monkeypatch.setattr(stamp, "RUN_DIR", tmp_path / ".run")

    assert stamp.check() == 1, "no stamp yet: run setup"
    stamp.write(detection=True)
    assert stamp.check() == 0, "fresh stamp: skip setup"

    (backend / ".env").write_text("DETECTOR_MODEL=yoloe-26s-seg\nOPENAI_API_KEY=changed\n")
    assert stamp.check() == 0, "an API key change doesn't need setup"

    (backend / ".env").write_text("DETECTOR_MODEL=yoloe-26m-seg\nOPENAI_API_KEY=changed\n")
    assert stamp.check() == 1, "another detector model needs its export"

    stamp.write(detection=True)
    (backend / "requirements-detect.txt").write_text("ultralytics==8.4.200\n")
    assert stamp.check() == 1, "a requirement changed"

    stamp.write(detection=True)
    (backend / "models" / "hand_landmarker.task").unlink()
    assert stamp.check() == 1, "a model file went missing"


def test_app_window_preallows_camera_and_mic_for_one_origin(tmp_path):
    app_window = _load("app_window")
    assert app_window.origin_pattern("http://localhost:8000/?token=abc") == "http://localhost:8000,*"
    assert app_window.origin_pattern("https://192.168.1.15:8443/") == "https://192.168.1.15:8443,*"
    assert app_window.origin_pattern("https://example.com/x") == "https://example.com:443,*"

    profile = tmp_path / "app-profile"
    (profile / "Default").mkdir(parents=True)
    existing = {"profile": {"content_settings": {"exceptions": {"media_stream_camera": {
        "https://10.0.0.2:8443,*": {"setting": 1}}}}}, "other": {"kept": True}}
    (profile / "Default" / "Preferences").write_text(json.dumps(existing))

    assert "allowed" in app_window.grant(profile, "http://localhost:8000/?token=abc")
    prefs = json.loads((profile / "Default" / "Preferences").read_text())
    exceptions = prefs["profile"]["content_settings"]["exceptions"]
    for setting in ("media_stream_camera", "media_stream_mic"):
        assert exceptions[setting]["http://localhost:8000,*"]["setting"] == 1
    assert exceptions["media_stream_camera"]["https://10.0.0.2:8443,*"]["setting"] == 1, "other grants kept"
    assert prefs["other"] == {"kept": True}, "the rest of the profile untouched"
    assert "already allowed" in app_window.grant(profile, "http://localhost:8000/")


def test_app_window_leaves_a_running_browsers_profile_alone(tmp_path, monkeypatch):
    app_window = _load("app_window")
    monkeypatch.setattr(app_window, "browser_running", lambda profile: True)
    assert "already open" in app_window.grant(tmp_path, "http://localhost:8000/")
    assert not (tmp_path / "Default" / "Preferences").exists()


def test_lan_all_prints_token_even_offline(monkeypatch, capsys):
    lan = _load("lan")
    monkeypatch.setattr(lan, "ensure_token", lambda: ("tok", False))
    monkeypatch.setattr(lan, "lan_ip", lambda: None)
    assert lan.main(["all"]) == 0
    assert capsys.readouterr().out.strip().split("|") == ["tok", "existing", "", "", "", ""]
