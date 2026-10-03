"""Registration, login and current-user endpoints."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import auth_rate_limit, get_current_user
from app.core.logging import get_logger
from app.core.security import (
    DUMMY_HASH, create_access_token, hash_password, verify_password,
)
from app.db.session import get_session
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("whale.auth")

_BAD_LOGIN = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Invalid email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
    responses={409: {"description": "Email already registered"}, 429: {"description": "Rate limited"}},
)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)) -> User:
    """Create an account. Passwords are 12-128 chars and stored only as Argon2id hashes."""
    if await session.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=body.email, password_hash=await asyncio.to_thread(hash_password, body.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    log.info("user_registered", user_id=user.id)
    return user


@router.post(
    "/login",
    response_model=TokenOut,
    dependencies=[Depends(auth_rate_limit)],
    responses={401: {"description": "Invalid credentials"}, 429: {"description": "Rate limited"}},
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenOut:
    """Exchange credentials for a short-lived bearer token. The error is identical whether the
    e-mail is unknown, the password is wrong, or the account is disabled."""
    user = await session.scalar(select(User).where(User.email == body.email))
    ok = await asyncio.to_thread(verify_password, body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        raise _BAD_LOGIN
    token, ttl = create_access_token(user.id)
    return TokenOut(access_token=token, expires_in=ttl)


@router.get(
    "/me", response_model=UserOut, responses={401: {"description": "Missing, invalid or expired token"}}
)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
