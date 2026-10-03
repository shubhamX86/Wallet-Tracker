import time

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from starlette.requests import Request

from app.api import dependencies
from app.core.config import Settings, get_settings

PW = "MySecurePassword123!"


async def register(api, email="demo@example.com", password=PW):
    return await api.post("/api/v1/auth/register", json={"email": email, "password": password})


async def login(api, email="demo@example.com", password=PW):
    return await api.post("/api/v1/auth/login", json={"email": email, "password": password})


async def auth_headers(api, email="demo@example.com"):
    await register(api, email)
    token = (await login(api, email)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ registration
async def test_register_success_returns_safe_user(api):
    r = await register(api)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "demo@example.com" and body["is_active"] is True and "id" in body
    assert not {"password", "password_hash"} & body.keys()
    assert "$argon2" not in r.text


async def test_password_stored_only_as_argon2_hash(api, db):
    await register(api)
    with db.connect() as c:
        stored = c.execute(text("SELECT password_hash FROM users")).scalar()
    assert stored.startswith("$argon2id$") and PW not in stored


async def test_email_is_normalized(api, db):
    r = await register(api, "  Demo@Example.COM ")
    assert r.status_code == 201 and r.json()["email"] == "demo@example.com"
    assert (await login(api, "DEMO@example.com")).status_code == 200


async def test_duplicate_email_conflict_even_with_different_case(api):
    assert (await register(api)).status_code == 201
    assert (await register(api)).status_code == 409
    assert (await register(api, "DEMO@EXAMPLE.COM")).status_code == 409


@pytest.mark.parametrize("email", ["not-an-email", "a@", "@example.com", "", "a b@example.com"])
async def test_invalid_email_rejected(api, email):
    assert (await register(api, email)).status_code == 422


@pytest.mark.parametrize("password", ["", "short", "a" * 11, "a" * 129])
async def test_weak_or_oversized_password_rejected(api, password):
    assert (await register(api, password=password)).status_code == 422


async def test_validation_errors_never_echo_the_password(api):
    secret = "tooShort1!"
    r = await register(api, password=secret)
    assert r.status_code == 422 and secret not in r.text
    assert r.json()["error"]["code"] == "validation_error"


async def test_password_boundaries_accepted(api):
    assert (await register(api, "min@example.com", "a" * 12)).status_code == 201
    assert (await register(api, "max@example.com", "a" * 128)).status_code == 201


# ------------------------------------------------------------------ login
async def test_login_success_returns_working_token(api):
    await register(api)
    r = await login(api)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 1800
    me = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "demo@example.com"


async def test_wrong_password_and_unknown_email_look_identical(api):
    await register(api)
    wrong = await login(api, password="WrongPassword123!")
    unknown = await login(api, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.headers["www-authenticate"] == "Bearer"


async def test_disabled_account_cannot_login_or_use_token(api, db):
    headers = await auth_headers(api)
    with db.begin() as c:
        c.execute(text("UPDATE users SET is_active = false"))
    assert (await login(api)).status_code == 401
    assert (await api.get("/api/v1/auth/me", headers=headers)).status_code == 401


# ------------------------------------------------------------------ /me and token handling
async def test_me_requires_a_token(api):
    r = await api.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer not.a.jwt", "Bearer ", "Basic abc", "garbage"])
async def test_me_rejects_invalid_tokens(api, header):
    assert (await api.get("/api/v1/auth/me", headers={"Authorization": header})).status_code == 401


async def test_me_rejects_expired_token(api):
    await register(api)
    now = int(time.time())
    token = jwt.encode({"sub": "1", "iat": now - 120, "exp": now - 60}, get_settings().jwt_secret, "HS256")
    r = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_token_for_deleted_user_rejected(api, db):
    headers = await auth_headers(api)
    with db.begin() as c:
        c.execute(text("DELETE FROM users"))
    assert (await api.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_errors_use_the_standard_envelope(api):
    body = (await api.get("/api/v1/auth/me")).json()
    assert body["error"]["code"] == "http_401"


# ------------------------------------------------------------------ rate limiting
class FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        pass


def _request(ip="1.2.3.4", headers=None):
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/auth/login", "query_string": b"",
        "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (ip, 5000),
    })


@pytest.fixture
def limiter(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(dependencies, "redis_client", fake)
    monkeypatch.setattr(
        dependencies, "get_settings", lambda: Settings(auth_rate_limit_per_minute=3, trust_proxy_headers=False)
    )
    return fake


async def test_rate_limit_blocks_after_limit_per_ip(limiter):
    for _ in range(3):
        await dependencies.auth_rate_limit(_request())
    with pytest.raises(HTTPException) as e:
        await dependencies.auth_rate_limit(_request())
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "60"
    await dependencies.auth_rate_limit(_request(ip="9.9.9.9"))  # other client unaffected


async def test_rate_limit_ignores_spoofed_proxy_header_by_default(limiter):
    for _ in range(3):
        await dependencies.auth_rate_limit(_request(headers={"x-real-ip": "5.5.5.5"}))
    with pytest.raises(HTTPException):  # still counted against the socket IP
        await dependencies.auth_rate_limit(_request(headers={"x-real-ip": "6.6.6.6"}))


async def test_rate_limit_uses_x_real_ip_only_when_trusted(monkeypatch):
    monkeypatch.setattr(dependencies, "redis_client", FakeRedis())
    monkeypatch.setattr(
        dependencies, "get_settings", lambda: Settings(auth_rate_limit_per_minute=1, trust_proxy_headers=True)
    )
    await dependencies.auth_rate_limit(_request(ip="10.0.0.1", headers={"x-real-ip": "5.5.5.5"}))
    await dependencies.auth_rate_limit(_request(ip="10.0.0.1", headers={"x-real-ip": "6.6.6.6"}))  # different user
    with pytest.raises(HTTPException):
        await dependencies.auth_rate_limit(_request(ip="10.0.0.1", headers={"x-real-ip": "5.5.5.5"}))


async def test_rate_limiter_fails_open_when_redis_is_down(monkeypatch):
    class Down:
        async def incr(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(dependencies, "redis_client", Down())
    await dependencies.auth_rate_limit(_request())  # must not raise
