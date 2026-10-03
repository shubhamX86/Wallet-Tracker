"""Wallet watchlist CRUD. Every query is scoped to the authenticated user."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.blockchain.addresses import supported_chain_ids
from app.db.session import get_session
from app.models import User, Wallet
from app.schemas.wallet import WalletCreate, WalletOut, WalletPage

router = APIRouter(prefix="/wallets", tags=["wallets"])

_401 = {401: {"description": "Missing, invalid or expired token"}}
_404 = {404: {"description": "Wallet not found (or not yours)"}}


async def _owned_wallet(session: AsyncSession, user: User, wallet_id: int) -> Wallet:
    wallet = await session.scalar(
        select(Wallet).where(Wallet.id == wallet_id, Wallet.user_id == user.id)
    )
    if wallet is None:  # same response for "doesn't exist" and "belongs to someone else"
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return wallet


@router.post(
    "/",
    response_model=WalletOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_401, 409: {"description": "Already tracking this address on this chain"},
               422: {"description": "Unsupported chain or malformed address"}},
)
async def add_wallet(
    body: WalletCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Wallet:
    """Track a public address. The address is validated and normalized for its chain."""
    exists = await session.scalar(
        select(Wallet.id).where(
            Wallet.user_id == user.id, Wallet.chain == body.chain, Wallet.address == body.address
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wallet already tracked on this chain")
    wallet = Wallet(user_id=user.id, address=body.address, chain=body.chain, label=body.label)
    session.add(wallet)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Wallet already tracked on this chain") from None
    return wallet


@router.get("/", response_model=WalletPage, responses=_401)
async def list_wallets(
    chain: Annotated[str | None, Query(description=f"One of: {', '.join(supported_chain_ids())}")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WalletPage:
    """Your wallets, newest first, paginated."""
    if chain is not None and chain not in supported_chain_ids():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported chain filter")
    where = [Wallet.user_id == user.id] + ([Wallet.chain == chain] if chain else [])
    total = await session.scalar(select(func.count()).select_from(Wallet).where(*where))
    rows = await session.scalars(
        select(Wallet).where(*where).order_by(Wallet.id.desc()).limit(limit).offset(offset)
    )
    return WalletPage(items=list(rows), total=total or 0, limit=limit, offset=offset)


@router.get("/{wallet_id}", response_model=WalletOut, responses={**_401, **_404})
async def get_wallet(
    wallet_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Wallet:
    return await _owned_wallet(session, user, wallet_id)


@router.delete(
    "/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**_401, **_404}
)
async def delete_wallet(
    wallet_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Stop tracking a wallet. Its stored transactions and sync state are removed with it."""
    wallet = await _owned_wallet(session, user, wallet_id)
    await session.delete(wallet)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
