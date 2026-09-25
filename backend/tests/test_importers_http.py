import httpx
import time


def test_403_then_200_retries(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403)
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx, "get", fake_get)

    from app.importers import http as importer_http

    resp = importer_http.get("https://example.com/foo", max_retries=2)
    assert resp.status_code == 200


def test_non_retryable_404_raises(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "get", fake_get)

    from app.importers import http as importer_http

    try:
        importer_http.get("https://example.com/not-found", max_retries=1)
    except RuntimeError as exc:
        assert "non-retryable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for 404")


def test_rate_floor_enforced(monkeypatch):
    # Fake monotonic clock + sleep to observe the enforced wait.
    clock = {"t": 1000.0}
    sleep_calls = []

    def fake_monotonic():
        return clock["t"]

    def fake_sleep(d):
        sleep_calls.append(d)
        # advance clock by the sleep duration so subsequent calls see the time pass
        clock["t"] += d

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx, "get", fake_get)

    from app.importers import http as importer_http

    # First call should not sleep (no prior timestamp)
    importer_http.get("https://example.com/a")
    # Immediate second call to same host should cause a sleep of at least MIN_DELAY_SEC
    importer_http.get("https://example.com/b")

    # There should be at least one sleep call with value >= MIN_DELAY_SEC
    assert any(d >= importer_http.MIN_DELAY_SEC for d in sleep_calls), f"sleep_calls={sleep_calls}"
