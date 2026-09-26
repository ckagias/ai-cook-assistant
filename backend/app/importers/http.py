"""Polite HTTP fetch helper for importers.

Retries transient errors (403, 429, 5xx) with exponential backoff and
enforces a MIN_DELAY_SEC floor between requests to the same host so we
don't hammer third-party sites. Uses a realistic desktop browser
`User-Agent` because Cloudflare on the target site rejects bare UAs.

See backend/app/importers/SITE_NOTES_akis.md for rationale around the UA
choice and Cloudflare behaviour.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import httpx

# A real desktop-browser UA string. Cloudflare on the target site rejects
# non-browser shaped user agents; documenting this choice in
# SITE_NOTES_akis.md rather than trying to "hide" it.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Minimum delay between requests to the same host (seconds)
MIN_DELAY_SEC = 1.0

# Default per-request timeout (seconds)
DEFAULT_TIMEOUT = 15.0

# In-memory per-host last-call timestamp (monotonic)
_last_call: dict[str, float] = {}
_lock = threading.Lock()


def _enforce_rate_floor(host: str) -> None:
    now = time.monotonic()
    with _lock:
        last = _last_call.get(host)
        if last is None:
            _last_call[host] = now
            return
        elapsed = now - last
        wait = MIN_DELAY_SEC - elapsed
        if wait > 0:
            time.sleep(wait)
            _last_call[host] = time.monotonic()
        else:
            _last_call[host] = now


def get(url: str, *, max_retries: int = 5, user_agent: str | None = None, follow_redirects: bool = True) -> httpx.Response:
    """GET `url` with polite retry/backoff and per-host rate-floor.

    `user_agent` defaults to the browser UA the Akis importer needs (SITE_NOTES_akis.md); the
    generic importer passes its own honest one. Redirects are followed - recipe sites commonly
    redirect to a canonical slug, and a 3xx would otherwise read as a hard failure.

    Raises RuntimeError on a non-retryable status or after exhausting
    retries.
    """
    parsed = urlparse(url)
    host = parsed.netloc

    attempt = 0
    backoff = 1.0
    while True:
        attempt += 1

        # Enforce the per-host minimum delay between requests.
        _enforce_rate_floor(host)

        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": user_agent or USER_AGENT},
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=follow_redirects,
            )
        except Exception as exc:
            # Network-level errors are treated as transient and retried.
            if attempt >= max_retries:
                raise RuntimeError(f"request failed after {attempt} attempts: {exc}") from exc
            time.sleep(backoff)
            backoff *= 2
            continue

        code = resp.status_code
        # Successful
        if 200 <= code < 300:
            return resp

        # Retryable transient statuses
        if code in (403, 429) or 500 <= code < 600:
            if attempt >= max_retries:
                raise RuntimeError(f"request to {url!r} failed after {attempt} attempts: status={code}")
            time.sleep(backoff)
            backoff *= 2
            continue

        # Non-retryable error
        raise RuntimeError(f"request to {url!r} returned non-retryable status: {code}")
