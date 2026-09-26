"""Local root CA in lan.py, and the public GET /ca.crt route."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID
from fastapi.testclient import TestClient

from app.main import app

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_lan():
    spec = importlib.util.spec_from_file_location("lan", SCRIPTS / "lan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_self_signed_leaf(cert_dir: Path, ip: str) -> None:
    """Reproduce the pre-CA format: issuer == subject."""
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
        .sign(key, hashes.SHA256())
    )
    (cert_dir / f"lan-{ip}-cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (cert_dir / f"lan-{ip}-key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


@pytest.fixture
def lan(tmp_path, monkeypatch):
    module = _load_lan()
    monkeypatch.setattr(module, "CERT_DIR", tmp_path)
    return module


def test_ca_has_basic_constraints_ca_true(lan):
    cert_path, _key_path = lan.ensure_ca()
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    ext = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
    assert ext.critical
    assert ext.value.ca is True
    usage = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
    assert usage.value.key_cert_sign
    assert usage.value.crl_sign
    crt = lan.CERT_DIR / "ca-cert.crt"
    assert crt.is_file()
    assert crt.read_bytes() == cert_path.read_bytes()


def test_ensure_ca_is_idempotent(lan):
    first, first_key = lan.ensure_ca()
    pem = first.read_bytes()
    second, second_key = lan.ensure_ca()
    assert (first, first_key) == (second, second_key)
    assert first.read_bytes() == pem


def test_leaf_is_signed_by_ca_and_san_contains_ip(lan):
    ip = "192.0.2.10"
    cert_path, _key_path, spki = lan.ensure_cert(ip)
    assert spki
    leaf = x509.load_pem_x509_certificate(cert_path.read_bytes())
    ca = x509.load_pem_x509_certificate((lan.CERT_DIR / "ca-cert.pem").read_bytes())
    assert leaf.issuer == ca.subject
    assert leaf.subject != leaf.issuer
    ca.public_key().verify(
        leaf.signature,
        leaf.tbs_certificate_bytes,
        padding.PKCS1v15(),
        leaf.signature_hash_algorithm,
    )
    san = leaf.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    ips = {str(addr) for addr in san.get_values_for_type(x509.IPAddress)}
    assert ip in ips
    assert "127.0.0.1" in ips
    eku = leaf.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku


def test_self_signed_leaf_is_regenerated_under_ca(lan):
    ip = "192.0.2.20"
    _write_self_signed_leaf(lan.CERT_DIR, ip)
    old = x509.load_pem_x509_certificate((lan.CERT_DIR / f"lan-{ip}-cert.pem").read_bytes())
    assert old.issuer == old.subject

    cert_path, _key_path, _spki = lan.ensure_cert(ip)
    leaf = x509.load_pem_x509_certificate(cert_path.read_bytes())
    ca = x509.load_pem_x509_certificate((lan.CERT_DIR / "ca-cert.pem").read_bytes())
    assert leaf.issuer == ca.subject
    assert leaf.serial_number != old.serial_number
    ca.public_key().verify(
        leaf.signature,
        leaf.tbs_certificate_bytes,
        padding.PKCS1v15(),
        leaf.signature_hash_algorithm,
    )


def test_ca_signed_leaf_is_not_rewritten(lan):
    ip = "192.0.2.30"
    cert_path, _key, _spki = lan.ensure_cert(ip)
    first = cert_path.read_bytes()
    cert_path2, _key2, _spki2 = lan.ensure_cert(ip)
    assert cert_path2.read_bytes() == first


@pytest.fixture
def client():
    return TestClient(app)


def test_ca_crt_404_when_missing(client, tmp_path, monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "CERTS_DIR", tmp_path)
    r = client.get("/ca.crt")
    assert r.status_code == 404


def test_ca_crt_200_with_right_content_type(client, tmp_path, monkeypatch):
    from app import main as main_mod

    body = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    (tmp_path / "ca-cert.crt").write_bytes(body)
    monkeypatch.setattr(main_mod, "CERTS_DIR", tmp_path)
    r = client.get("/ca.crt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-x509-ca-cert")
    assert r.content == body


def test_ca_crt_is_not_behind_pairing_token(client, tmp_path, monkeypatch):
    from app import main as main_mod

    (tmp_path / "ca-cert.crt").write_bytes(b"CERT")
    monkeypatch.setattr(main_mod, "CERTS_DIR", tmp_path)
    monkeypatch.setenv("BACKEND_PAIRING_TOKEN", "secret")
    r = client.get("/ca.crt")
    assert r.status_code == 200
    assert r.content == b"CERT"
