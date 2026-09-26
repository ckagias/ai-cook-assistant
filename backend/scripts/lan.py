#!/usr/bin/env python3
"""LAN helpers shared by setup-window.sh and setup-window.ps1, so both launchers behave the same.

  python scripts/lan.py ip            -> this machine's LAN IPv4 address (exit 1 if offline)
  python scripts/lan.py cert <ip>     -> ensures certs/lan-<ip>-{cert,key}.pem exist (one per IP,
                                         never deleted), prints "<cert>|<key>|<spki-sha256-base64>"
  python scripts/lan.py token         -> ensures BACKEND_PAIRING_TOKEN is set in backend/.env,
                                         prints "<token>|generated" or "<token>|existing"
  python scripts/lan.py all           -> token, then ip + cert when online, in one line (start.*)

The SPKI hash lets the app window trust exactly this certificate
(--ignore-certificate-errors-spki-list) instead of switching certificate checks off.

Leaf certs are signed by a local root CA (certs/ca-cert.pem). A phone that
installs that CA once (GET /ca.crt) trusts every later per-IP leaf, including
after a DHCP address change.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import re
import secrets
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
CERT_DIR = BACKEND_DIR / "certs"
ENV_PATH = BACKEND_DIR / ".env"

# Chrome/Apple reject server certs valid longer than this.
LEAF_DAYS = 825
CA_DAYS = 3650


def lan_ip() -> str | None:
    # LAN_IP pins the address, e.g. the laptop's own hotspot (192.168.137.1) that start.ps1
    # turns on, so the QR codes printed for the slides never change.
    if os.getenv("LAN_IP"):
        return os.environ["LAN_IP"]
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


def _ca_common_name() -> str:
    # X.509 CN is capped at 64 characters.
    host = socket.gethostname() or "local"
    prefix, suffix = "Cooking Assistant Local CA (", ")"
    return f"{prefix}{host[: 64 - len(prefix) - len(suffix)]}{suffix}"


def _ca_paths() -> tuple[Path, Path, Path]:
    return CERT_DIR / "ca-cert.pem", CERT_DIR / "ca-key.pem", CERT_DIR / "ca-cert.crt"


def ensure_ca() -> tuple[Path, Path]:
    """Create the local root CA once. Returns (ca-cert.pem, ca-key.pem).

    Also writes ca-cert.crt (same PEM bytes) so Android's file picker accepts it.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    CERT_DIR.mkdir(exist_ok=True)
    cert_path, key_path, crt_path = _ca_paths()
    if cert_path.exists() and key_path.exists():
        if not crt_path.exists():
            crt_path.write_bytes(cert_path.read_bytes())
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _ca_common_name())])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_path.write_bytes(pem)
    crt_path.write_bytes(pem)
    return cert_path, key_path


def ensure_cert(ip: str) -> tuple[Path, Path, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ipaddress.ip_address(ip)  # refuse anything that isn't an IP before it becomes a file name
    CERT_DIR.mkdir(exist_ok=True)
    ca_cert_path, ca_key_path = ensure_ca()
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)

    cert_path = CERT_DIR / f"lan-{ip}-cert.pem"
    key_path = CERT_DIR / f"lan-{ip}-key.pem"
    if cert_path.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        # Reissue leftovers: the old self-signed format (issuer == subject), or a
        # leaf signed by a previous CA after the CA files were recreated.
        if cert.issuer == ca_cert.subject:
            return cert_path, key_path, spki_sha256(cert)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Cooking Assistant ({ip})")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=LEAF_DAYS))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address(ip)),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
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
    elif argv[:1] == ["all"]:
        # One process for start.ps1/start.sh: "<token>|<generated|existing>|<ip>|<cert>|<key>|<spki>",
        # the last four empty when offline (the app then runs on localhost only).
        token, generated = ensure_token()
        ip = lan_ip()
        cert, key, spki = ensure_cert(ip) if ip else ("", "", "")
        print(f"{token}|{'generated' if generated else 'existing'}|{ip or ''}|{cert}|{key}|{spki}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
