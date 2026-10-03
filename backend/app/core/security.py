"""Password hashing (Argon2id) and short-lived JWT access tokens."""
from __future__ import annotations

import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()  # argon2id with library defaults
# Verified against when the e-mail is unknown, so login timing doesn't reveal which e-mails exist.
DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, *, now: float | None = None) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    s = get_settings()
    iat = int(now if now is not None else time.time())
    ttl = s.access_token_expire_minutes * 60
    token = jwt.encode(
        {"sub": str(user_id), "iat": iat, "exp": iat + ttl}, s.jwt_secret, algorithm=s.jwt_algorithm
    )
    return token, ttl


def decode_access_token(token: str) -> int | None:
    """User id from a valid token, else None. Never raises; never says *why* it failed."""
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],  # pinned: rejects alg=none / other algorithms
            options={"require": ["exp", "iat", "sub"]},
        )
        sub = claims["sub"]
        return int(sub) if isinstance(sub, str) and sub.isdigit() else None
    except jwt.PyJWTError:
        return None
