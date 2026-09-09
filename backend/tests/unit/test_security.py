from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("my-secret-password")
    assert hashed != "my-secret-password"
    assert verify_password("my-secret-password", hashed)


def test_verify_wrong_password():
    hashed = hash_password("correct-password")
    assert not verify_password("wrong-password", hashed)


def test_create_and_decode_token():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_decode_expired_token():
    settings = get_settings()
    payload = {
        "sub": "user-123",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert decode_access_token(token) is None


def test_decode_tampered_token():
    token = create_access_token("user-123")
    replacement = "AB" if token[-2:] != "AB" else "CD"
    tampered = token[:-2] + replacement
    assert decode_access_token(tampered) is None


def test_decode_empty_string():
    assert decode_access_token("") is None


def test_hash_is_not_reversible_plaintext():
    hashed = hash_password("password123")
    assert "password123" not in hashed