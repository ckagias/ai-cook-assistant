#!/usr/bin/env python3
"""LAN helpers shared by setup-window.sh and setup-window.ps1, so both launchers behave the same.

  python scripts/lan.py ip            -> this machine's LAN IPv4 address (exit 1 if offline)
  python scripts/lan.py cert <ip>     -> ensures certs/lan-<ip>-{cert,key}.pem exist (one per IP,
                                         never deleted), prints "<cert>|<key>|<spki-sha256-base64>"
  python scripts/lan.py token         -> ensures BACKEND_PAIRING_TOKEN is set in backend/.env,
                                         prints "<token>|generated" or "<token>|existing"

The SPKI hash lets the app window trust exactly this certificate
(--ignore-certificate-errors-spki-list) instead of switching certificate checks off.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import secrets
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
CERT_DIR = BACKEND_DIR / "certs"
ENV_PATH = BACKEND_DIR / ".env"


def lan_ip() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # a routing lookup only - nothing is sent
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


def spki_sha256(cert) -> str:
    from cryptography.hazmat.primitives import serialization

    der = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(hashlib.sha256(der).digest()).decode("ascii")


def ensure_cert(ip: str) -> tuple[Path, Path, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    ipaddress.ip_address(ip)  # refuse anything that isn't an IP before it becomes a file name
    CERT_DIR.mkdir(exist_ok=True)
    cert_path = CERT_DIR / f"lan-{ip}-cert.pem"
    key_path = CERT_DIR / f"lan-{ip}-key.pem"
    if cert_path.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        return cert_path, key_path, spki_sha256(cert)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Cooking Assistant ({ip})")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address(ip)),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path, spki_sha256(cert)


def ensure_token() -> tuple[str, bool]:
    text = ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.exists() else ""
    match = re.search(r"^BACKEND_PAIRING_TOKEN=(.*)$", text, re.M)
    if match and match.group(1).strip():
        return match.group(1).strip(), False
    token = secrets.token_urlsafe(24)
    if match:
        text = text[: match.start()] + f"BACKEND_PAIRING_TOKEN={token}" + text[match.end():]
    else:
        text = text.rstrip("\n") + f"\nBACKEND_PAIRING_TOKEN={token}\n"
    ENV_PATH.write_text(text, encoding="utf-8", newline="")  # keep the file's own line endings
    return token, True


def main(argv: list[str]) -> int:
    if argv[:1] == ["ip"]:
        ip = lan_ip()
        if not ip:
            print("no network connection found", file=sys.stderr)
            return 1
        print(ip)
    elif argv[:1] == ["cert"] and len(argv) == 2:
        cert, key, spki = ensure_cert(argv[1])
        print(f"{cert}|{key}|{spki}")
    elif argv[:1] == ["token"]:
        token, generated = ensure_token()
        print(f"{token}|{'generated' if generated else 'existing'}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
