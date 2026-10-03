import time

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    DUMMY_HASH, create_access_token, decode_access_token, hash_password, verify_password,
)


def test_hash_is_argon2id_salted_and_verifies():
    h1, h2 = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert h1.startswith("$argon2id$") and h1 != h2  # unique salts
    assert "correct horse" not in h1
    assert verify_password("correct horse battery", h1)


def test_wrong_password_and_garbage_hash_fail_closed():
    h = hash_password("correct horse battery")
    assert not verify_password("wrong password!!", h)
    assert not verify_password("anything", "not-a-hash")
    assert not verify_password("anything", "")
    assert not verify_password("not-a-real-password", "$argon2id$garbage")
    assert verify_password("not-a-real-password", DUMMY_HASH)  # the timing-equaliser hash is real


def test_token_roundtrip_and_claims():
    token, ttl = create_access_token(42)
    claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "42" and claims["exp"] - claims["iat"] == ttl == 30 * 60
    assert decode_access_token(token) == 42


def _forge(**overrides):
    s = get_settings()
    now = int(time.time())
    claims = {"sub": "1", "iat": now, "exp": now + 600, **overrides}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def test_expired_token_rejected():
    assert decode_access_token(_forge(exp=int(time.time()) - 10)) is None


@pytest.mark.parametrize("missing", ["exp", "iat", "sub"])
def test_missing_required_claims_rejected(missing):
    assert decode_access_token(_forge(**{missing: None})) is None


@pytest.mark.parametrize("sub", ["abc", "-1", "1.5", "", "1 OR 1=1"])
def test_non_numeric_subject_rejected(sub):
    assert decode_access_token(_forge(sub=sub)) is None


def test_wrong_secret_wrong_algorithm_and_none_alg_rejected():
    now = int(time.time())
    claims = {"sub": "1", "iat": now, "exp": now + 600}
    assert decode_access_token(jwt.encode(claims, "x" * 40, algorithm="HS256")) is None
    assert decode_access_token(jwt.encode(claims, get_settings().jwt_secret, algorithm="HS512")) is None
    assert decode_access_token(jwt.encode(claims, key=None, algorithm="none")) is None


@pytest.mark.parametrize("junk", ["", "abc", "a.b.c", "Bearer x", "x" * 5000])
def test_malformed_tokens_rejected(junk):
    assert decode_access_token(junk) is None
