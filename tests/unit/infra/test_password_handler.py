"""Tests for infrastructure.auth.password_handler."""

from __future__ import annotations

import pytest

from infrastructure.auth.password_handler import PasswordHandler


@pytest.fixture
def handler() -> PasswordHandler:
    # Use lower cost for fast tests
    return PasswordHandler(time_cost=1, memory_cost=16384, parallelism=1)


class TestHashPassword:
    def test_returns_argon2id_string(self, handler: PasswordHandler) -> None:
        hashed = handler.hash_password("s3cret!")
        assert isinstance(hashed, str)
        assert hashed.startswith("$argon2id$")

    def test_different_hashes_for_same_input(self, handler: PasswordHandler) -> None:
        """Each call uses a random salt, so outputs must differ."""
        h1 = handler.hash_password("same-password")
        h2 = handler.hash_password("same-password")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password_returns_true(self, handler: PasswordHandler) -> None:
        hashed = handler.hash_password("correct-horse")
        assert handler.verify_password("correct-horse", hashed) is True

    def test_wrong_password_returns_false(self, handler: PasswordHandler) -> None:
        hashed = handler.hash_password("correct-horse")
        assert handler.verify_password("wrong-horse", hashed) is False

    def test_malformed_hash_returns_false(self, handler: PasswordHandler) -> None:
        assert handler.verify_password("anything", "not-a-valid-hash") is False
