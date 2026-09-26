#!/usr/bin/env python3
"""Serve the app on this computer and on the local network from ONE process - one detection
model in memory, one warm-up.

  python scripts/serve.py                                   # http://localhost:8000
  python scripts/serve.py --lan-port 8443 --cert C --key K  # + https://<LAN IP>:8443 for phones

localhost stays plain HTTP: browsers treat it as secure (camera allowed) and there is no
certificate warning. The LAN needs HTTPS for the camera, with the certificate from scripts/lan.py.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import uvicorn  # noqa: E402


async def serve_all(configs: list[uvicorn.Config]) -> None:
    await asyncio.gather(*(uvicorn.Server(c).serve() for c in configs))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.getenv("BACKEND_PORT") or 8000))
    ap.add_argument("--lan-port", type=int, default=None)
    ap.add_argument("--cert", default=None)
    ap.add_argument("--key", default=None)
    ap.add_argument("--detection", choices=["auto", "on", "off"], default="auto",
                    help="auto (default): on whenever ultralytics + mediapipe are installed")
    args = ap.parse_args()

    # backend/.env, without overriding what the launcher already set (e.g. the pairing token).
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env", override=False)
    if args.detection == "auto":
        installed = importlib.util.find_spec("ultralytics") and importlib.util.find_spec("mediapipe")
        os.environ["DETECTION_ENABLED"] = "true" if installed else "false"
    else:
        os.environ["DETECTION_ENABLED"] = "true" if args.detection == "on" else "false"

    from app.main import app

    configs = [uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="info")]
    if args.lan_port:
        if not (args.cert and args.key):
            ap.error("--lan-port needs --cert and --key (python scripts/lan.py cert <ip>)")
        # lifespan off: the app's startup (database, detection warm-up) runs once, on the first.
        configs.append(uvicorn.Config(app, host="0.0.0.0", port=args.lan_port, ssl_certfile=args.cert,
                                      ssl_keyfile=args.key, log_level="info", lifespan="off"))
    try:
        asyncio.run(serve_all(configs))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
