"""Shared FastAPI dependencies: current user and auth-endpoint rate limiting."""
import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User

log = get_logger("whale.auth")
_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise _unauthorized()
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise _unauthorized()
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def client_ip(request: Request) -> str:
    """Behind our nginx the real client is in X-Real-IP. Only trusted when explicitly enabled,
    otherwise the header is attacker-controlled."""
    if get_settings().trust_proxy_headers:
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return request.client.host if request.client else "unknown"


async def auth_rate_limit(request: Request) -> None:
    """Fixed-window per-IP limiter (Redis). Fails open if Redis is down, and logs it."""
    limit = get_settings().auth_rate_limit_per_minute
    key = f"rl:auth:{request.url.path}:{client_ip(request)}:{int(time.time() // 60)}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 70)
    except Exception:
        log.warning("rate_limiter_unavailable")
        return
    if count > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests", headers={"Retry-After": "60"}
        )
