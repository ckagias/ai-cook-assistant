"""HTML utilities for importer parsing (Phase 4).

Provides `extract_next_data(html, src_url=None)` to extract the JSON blob
from Next.js pages (`__NEXT_DATA__`) and `strip_html(text)` to decode
HTML entities and remove tags.
"""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Optional


_SCRIPT_RE = re.compile(r"<script[^>]*id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_next_data(html: str, src_url: Optional[str] = None) -> dict:
    """Extract and parse the JSON inside <script id="__NEXT_DATA__">.

    Raises ValueError with a helpful message (including `src_url` if
    provided) when the tag is missing or the JSON fails to parse.
    """
    m = _SCRIPT_RE.search(html)
    if not m:
        if src_url:
            raise ValueError(f"__NEXT_DATA__ script tag missing in HTML fetched from {src_url}")
        raise ValueError("__NEXT_DATA__ script tag missing in HTML")

    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception as exc:
        if src_url:
            raise ValueError(f"failed to parse __NEXT_DATA__ JSON from {src_url}: {exc}") from exc
        raise ValueError(f"failed to parse __NEXT_DATA__ JSON: {exc}") from exc


def strip_html(text: Optional[str]) -> str:
    """Decode HTML entities and strip tags. Returns empty string for None."""
    if not text:
        return ""
    # Decode entities first (e.g. &deg;, &eacute;)
    un = unescape(text)
    # Remove tags
    stripped = _TAG_RE.sub("", un)
    # Collapse whitespace
    return " ".join(stripped.split())
