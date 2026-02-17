"""Tests for infrastructure.auth.jwt_handler."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError

from infrastructure.auth.jwt_handler import JWTConfig, JWTHandler

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    """Generate an RSA key pair once for the entire module."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture
def jwt_handler(rsa_keypair: tuple[str, str]) -> JWTHandler:
    private_pem, public_pem = rsa_keypair
    return JWTHandler(private_key=private_pem, public_key=public_pem)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestCreateAccessToken:
    def test_returns_jwt_string(self, jwt_handler: JWTHandler) -> None:
        token = jwt_handler.create_access_token(
            user_id="u-1",
            tenant_id="t-1",
            role="ADMIN",
        )
        assert isinstance(token, str)
        # JWTs have three dot-separated segments
        assert token.count(".") == 2


class TestDecodeToken:
    def test_contains_expected_claims(self, jwt_handler: JWTHandler) -> None:
        token = jwt_handler.create_access_token(
            user_id="u-42",
            tenant_id="t-7",
            role="OWNER",
        )
        claims = jwt_handler.decode_token(token)

        assert claims["sub"] == "u-42"
        assert claims["tenant_id"] == "t-7"
        assert claims["role"] == "OWNER"
        assert claims["iss"] == "eu-mt-platform"
        assert "iat" in claims
        assert "exp" in claims

    def test_expired_token_raises(self, rsa_keypair: tuple[str, str]) -> None:
        private_pem, public_pem = rsa_keypair
        config = JWTConfig(access_token_expire_minutes=-1)
        handler = JWTHandler(private_key=private_pem, public_key=public_pem, config=config)

        token = handler.create_access_token(
            user_id="u-1",
            tenant_id="t-1",
            role="VIEWER",
        )
        with pytest.raises(JWTError):
            handler.decode_token(token)


class TestVerifyToken:
    def test_valid_token_returns_true(self, jwt_handler: JWTHandler) -> None:
        token = jwt_handler.create_access_token(
            user_id="u-1",
            tenant_id="t-1",
            role="MEMBER",
        )
        assert jwt_handler.verify_token(token) is True

    def test_garbage_returns_false(self, jwt_handler: JWTHandler) -> None:
        assert jwt_handler.verify_token("not.a.jwt") is False
