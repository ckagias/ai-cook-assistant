import json
import pytest

from app.importers import html_utils


def test_strip_html_decodes_and_strips():
    s = "Mix the batter &ndash; until <strong>smooth</strong>. Temperature 200&deg;C"
    out = html_utils.strip_html(s)
    assert "ndash" not in out
    assert "smooth" in out
    assert "200°C" in out or "200°C" in out


def test_strip_html_none_and_plain():
    assert html_utils.strip_html(None) == ""
    assert html_utils.strip_html("plain text") == "plain text"


def test_extract_next_data_success_and_error():
    payload = {"foo": "bar"}
    html = f"<html><head><script id=\"__NEXT_DATA__\">{json.dumps(payload)}</script></head></html>"
    parsed = html_utils.extract_next_data(html)
    assert parsed == payload

    with pytest.raises(ValueError):
        html_utils.extract_next_data("<html></html>")
