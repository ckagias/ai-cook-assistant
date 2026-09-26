#!/usr/bin/env python3
"""Print a QR code for the phone pairing URL.

  python scripts/pairing_qr.py --url URL --png PATH   # launcher: exact URL already built
  python scripts/pairing_qr.py                        # standalone: rebuild from env + LAN IP

Standalone never writes a pairing token. If BACKEND_PAIRING_TOKEN is empty the
URL has no ?token= and a note is printed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def parse_lan_all(line: str) -> tuple[str, str]:
    """token, ip from a `lan.py all` line: token|state|ip|cert|key|spki."""
    parts = line.strip().split("|")
    token = parts[0] if parts else ""
    ip = parts[2] if len(parts) > 2 else ""
    return token, ip


def phone_url(ip: str, port: int, token: str) -> tuple[str, str | None]:
    """Same shape the launchers print: ?token=...&detect=1, token omitted if blank."""
    if not ip:
        raise ValueError("no LAN IP")
    if token:
        return f"https://{ip}:{port}/?token={token}&detect=1", None
    return (
        f"https://{ip}:{port}/?detect=1",
        "BACKEND_PAIRING_TOKEN is unset - URL has no ?token= (not inventing one).",
    )


def _standalone_url(port: int) -> tuple[str, str | None]:
    # Read the token from .env only - lan.py all would call ensure_token() and write one.
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env", override=False)
    token = (os.getenv("BACKEND_PAIRING_TOKEN") or "").strip()
    sys.path.insert(0, str(BACKEND_DIR / "scripts"))
    from lan import lan_ip  # noqa: E402

    ip = lan_ip()
    if not ip:
        raise ValueError("no network connection found")
    return phone_url(ip, port, token)


def render(url: str, png: Path) -> int:
    try:
        import qrcode
    except ImportError:
        print("      (QR skipped - qrcode not installed; re-run setup.sh)")
        return 0

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stdout, invert=True)
    png.parent.mkdir(parents=True, exist_ok=True)
    qr.make_image(fill_color="black", back_color="white").save(png)
    print(f"      PNG: {png}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=None, help="pairing URL (start.sh / start.ps1 pass the one they printed)")
    ap.add_argument("--png", default=None, help="where to write the PNG (default: .run/pairing.png)")
    ap.add_argument("--lan-all", default=None, help=argparse.SUPPRESS)  # tests: a mocked `lan.py all` line
    args = ap.parse_args(argv)

    port = int(os.getenv("BACKEND_HTTPS_PORT") or 8443)
    png = Path(args.png) if args.png else BACKEND_DIR.parent / ".run" / "pairing.png"
    note = None
    url = args.url
    if not url:
        try:
            if args.lan_all is not None:
                token, ip = parse_lan_all(args.lan_all)
                url, note = phone_url(ip, port, token)
            else:
                url, note = _standalone_url(port)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    if note:
        print(note)
    return render(url, png)


if __name__ == "__main__":
    raise SystemExit(main())
