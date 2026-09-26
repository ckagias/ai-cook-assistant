#!/usr/bin/env python3
"""Remember that setup finished, so start.cmd / start.sh can skip it and open in seconds.

  python scripts/setup_stamp.py write [--detection]   # the end of a successful setup
  python scripts/setup_stamp.py check                 # exit 0 = ready, 1 = run setup first

The stamp fingerprints everything setup acts on: the requirement files, the detection
vocabulary and settings (they name the exported model), this Python and this venv. Change any of
them and the next start runs setup again - which itself only fetches what changed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
RUN_DIR = BACKEND_DIR.parent / ".run"
DETECTOR_KEYS = ("DETECTOR_MODEL", "DETECTOR_IMGSZ", "DETECTOR_FORMAT", "HANDS_BACKEND")


def stamp_path() -> Path:
    # One per venv: Windows and WSL keep separate environments of the same checkout.
    venv = hashlib.sha256(sys.prefix.encode()).hexdigest()[:12]
    return RUN_DIR / f"setup-{venv}.stamp"


def _env_lines() -> list[str]:
    env = BACKEND_DIR / ".env"
    if not env.exists():
        return []
    lines = env.read_text(encoding="utf-8", errors="replace").splitlines()
    return sorted(line.strip() for line in lines if line.strip().split("=", 1)[0] in DETECTOR_KEYS)


def fingerprint(detection: bool) -> str:
    h = hashlib.sha256()
    files = ["requirements.txt"] + (["requirements-detect.txt", "app/detection/vocabulary.json"] if detection else [])
    for name in files:
        h.update(name.encode() + b"\0" + (BACKEND_DIR / name).read_bytes())
    if detection:
        h.update("\n".join(_env_lines()).encode())
    h.update(f"{sys.version}\0{sys.prefix}\0{detection}".encode())
    return h.hexdigest()


def write(detection: bool) -> int:
    RUN_DIR.mkdir(exist_ok=True)
    stamp_path().write_text(json.dumps({"fingerprint": fingerprint(detection), "detection": detection}), encoding="utf-8")
    return 0


def check() -> int:
    try:
        stamp = json.loads(stamp_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 1
    if not (BACKEND_DIR / ".env").exists():
        return 1
    if stamp.get("detection") and not (BACKEND_DIR / "models" / "hand_landmarker.task").exists():
        return 1
    return 0 if stamp.get("fingerprint") == fingerprint(bool(stamp.get("detection"))) else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["write"]:
        sys.exit(write("--detection" in args))
    if args[:1] == ["check"]:
        sys.exit(check())
    print(__doc__, file=sys.stderr)
    sys.exit(2)
