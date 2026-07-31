import base64
import datetime

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from fastapi.testclient import TestClient

from app.main import app


def make_pfx_base64(password: bytes = b"secret") -> str:
    """Gera um PKCS12 (.pfx) autoassinado em base64 — para testar o mTLS sem rede."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    enc = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
    data = pkcs12.serialize_key_and_certificates(b"test", key, cert, None, enc)
    return base64.b64encode(data).decode()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def cobranca_payload() -> dict:
    return {
        "valor": "1000.00",
        "vencimento": "2026-07-10",
        "nosso_numero": "123",
        "seu_numero": "A-1",
        "pagador": {"nome": "Fulano", "documento": "12345678901"},
    }


@pytest.fixture
def pfx_b64() -> str:
    return make_pfx_base64()
