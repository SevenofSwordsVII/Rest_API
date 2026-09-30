"""Unit tests for security primitives: Argon2id password hashing and PyJWT tokens."""

from datetime import timedelta

import jwt
import pytest

from src.core.security import (
    create_access_token,
    decode_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    password = "MySecurePassword!2026"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_token_hashing_sha256() -> None:
    raw_token = generate_secure_token(32)
    hashed_1 = hash_token(raw_token)
    hashed_2 = hash_token(raw_token)

    assert len(hashed_1) == 64  # SHA-256 hex digest length
    assert hashed_1 == hashed_2
    assert hashed_1 != raw_token


def test_create_and_decode_access_token() -> None:
    subject = "user-uuid-12345"
    claims = {"role": "ADMIN", "org_id": "org-uuid-67890"}

    token = create_access_token(subject=subject, claims=claims)
    decoded = decode_access_token(token)

    assert decoded["sub"] == subject
    assert decoded["role"] == "ADMIN"
    assert decoded["org_id"] == "org-uuid-67890"
    assert "exp" in decoded
    assert "iat" in decoded


def test_expired_token_raises_jwt_error() -> None:
    subject = "user-uuid-expired"
    token = create_access_token(
        subject=subject,
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_raises_jwt_error() -> None:
    token = create_access_token(subject="user-uuid-12345")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)


def test_invalid_token_string_raises_jwt_error() -> None:
    with pytest.raises(jwt.DecodeError):
        decode_access_token("not-a-valid-jwt-token")


def test_argon2_verify_with_malformed_hash() -> None:
    assert verify_password("Password123!", "not-a-valid-argon2-hash") is False
