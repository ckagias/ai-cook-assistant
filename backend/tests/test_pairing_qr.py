"""URL building for pairing_qr.py - no qrcode, no network."""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("pairing_qr", SCRIPTS / "pairing_qr.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phone_url_includes_token_when_set():
    qr = _load()
    url, note = qr.phone_url("192.168.1.15", 8443, "abc123")
    assert url == "https://192.168.1.15:8443/?token=abc123&detect=1"
    assert note is None


def test_phone_url_omits_token_when_blank():
    qr = _load()
    url, note = qr.phone_url("10.0.0.2", 8443, "")
    assert url == "https://10.0.0.2:8443/?detect=1"
    assert "token=" not in url
    assert note and "unset" in note


def test_parse_lan_all_with_token():
    qr = _load()
    token, ip = qr.parse_lan_all("sekrit|existing|192.168.1.15|/c.pem|/k.pem|hash")
    assert token == "sekrit"
    assert ip == "192.168.1.15"
    url, note = qr.phone_url(ip, 8443, token)
    assert url == "https://192.168.1.15:8443/?token=sekrit&detect=1"
    assert note is None


def test_parse_lan_all_blank_token_does_not_invent_one():
    qr = _load()
    token, ip = qr.parse_lan_all("|existing|10.0.0.2|||")
    assert token == ""
    url, note = qr.phone_url(ip, 8443, token)
    assert "token=" not in url
    assert note
