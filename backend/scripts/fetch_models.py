#!/usr/bin/env python3
"""Make sure the models the configured detector needs are on disk (download / export once).

Usage: python scripts/fetch_models.py      # reads DETECTOR_* / HANDS_BACKEND from backend/.env

Only ever adds files under backend/models/: a different model or input size is exported next to
the existing ones, which stay usable (switching back in .env costs nothing).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(BACKEND_DIR / ".env")
    except ImportError:
        pass
    try:
        from app.detection import detector, hands
        from app.detection.service import DetectionConfig
    except ImportError as exc:
        print(f"  detection dependencies not installed ({exc.name}) - skipping model download")
        return 0

    config = DetectionConfig.from_env()
    before = set(p.name for p in detector.MODELS_DIR.glob("**/*")) if detector.MODELS_DIR.exists() else set()
    t0 = time.perf_counter()
    detector.load_detector(config.model, config.imgsz, config.fmt, rect=config.rect)  # downloads + exports only if missing
    if config.hands in ("mediapipe", "hybrid"):
        hands.ensure_hand_model()
    after = set(p.name for p in detector.MODELS_DIR.glob("**/*"))
    new = sorted(after - before)
    label = f"{config.model}@{config.imgsz}{'r' if config.rect else ''}/{config.fmt}, hands: {config.hands}"
    if new:
        print(f"  models ready for {label} in {time.perf_counter() - t0:.0f}s - added: {', '.join(new[:6])}{' ...' if len(new) > 6 else ''}")
    else:
        print(f"  models for {label}: already on disk.")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
