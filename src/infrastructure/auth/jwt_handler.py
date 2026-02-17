"""
JWT token management for the EU Multi-Tenant Platform.

Handles creation, decoding, and verification of RS256-signed JWT tokens
with tenant-aware claims for secure multi-tenant authentication.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt


@dataclass(frozen=True)
class JWTConfig:
    """Configuration for JWT token generation and validation."""

    algorithm: str = "RS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    issuer: str = "eu-mt-platform"


class JWTHandler:
    """
    Manages JWT token lifecycle: creation, decoding, and verification.

    Tokens are signed with RS256 (asymmetric) so that services holding only the
    public key can verify tokens without being able to forge them.
    """

    def __init__(
        self,
        private_key: str,
        public_key: str,
        config: Optional[JWTConfig] = None,
    ) -> None:
        self._private_key = private_key
        self._public_key = public_key
        self._config = config or JWTConfig()

    # ------------------------------------------------------------------
    # Token creation
    # ------------------------------------------------------------------

    def create_access_token(
        self,
        user_id: str,
        tenant_id: str,
        role: str,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create a short-lived access token carrying identity and role claims."""

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=self._config.access_token_expire_minutes)

        payload: dict[str, Any] = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "role": role,
            "iat": now,
            "exp": expires,
            "iss": self._config.issuer,
            "jti": str(uuid.uuid4()),
            "token_type": "access",
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(
            payload,
            self._private_key,
            algorithm=self._config.algorithm,
        )

    def create_refresh_token(
        self,
        user_id: str,
        tenant_id: str,
    ) -> str:
        """Create a long-lived refresh token (minimal claims)."""

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self._config.refresh_token_expire_days)

        payload: dict[str, Any] = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "iat": now,
            "exp": expires,
            "iss": self._config.issuer,
            "jti": str(uuid.uuid4()),
            "token_type": "refresh",
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm=self._config.algorithm,
        )

    # ------------------------------------------------------------------
    # Token consumption
    # ------------------------------------------------------------------

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decode and validate a JWT token.

        Raises ``jose.JWTError`` when the token is invalid, expired, or has
        an unexpected issuer.
        """

        claims: dict[str, Any] = jwt.decode(
            token,
            self._public_key,
            algorithms=[self._config.algorithm],
            issuer=self._config.issuer,
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
        return claims

    def verify_token(self, token: str) -> bool:
        """Return *True* when the token is structurally valid and not expired."""

        try:
            self.decode_token(token)
            return True
        except JWTError:
            return False
