from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Raw integer base units. 78 digits holds uint256 (max ~1.16e77) exactly; no floats anywhere.
RawAmount = Numeric(78, 0)


class Transaction(TimestampMixin, Base):
    """One observed movement involving a tracked wallet.

    A single on-chain transaction can contain several movements for the same wallet
    (native transfer + N token transfers; several SPL instructions), so identity is
    (wallet, chain, tx_hash, transfer_index) where transfer_index is the log index (EVM) or
    instruction index (Solana); 0 for the native/top-level movement.

    Unknown values are NULL, never 0. `value`/`fee` are raw base units (wei, lamports, token
    units); use token_decimals / the chain's native decimals to convert.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "wallet_id", "chain", "tx_hash", "transfer_index",
            name="uq_transactions_wallet_chain_hash_index",
        ),
        CheckConstraint(
            "status IN ('success', 'failed', 'pending')", name="status_valid"
        ),
        CheckConstraint("transfer_index >= 0", name="transfer_index_nonneg"),
        Index("ix_transactions_wallet_id_timestamp", "wallet_id", "timestamp"),
        Index("ix_transactions_wallet_id_block_number", "wallet_id", "block_number"),
        Index("ix_transactions_chain_tx_hash", "chain", "tx_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # EVM hash / Solana signature
    transfer_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    block_number: Mapped[int | None] = mapped_column(BigInteger)  # block (EVM) or slot (Solana)
    from_address: Mapped[str | None] = mapped_column(String(128))
    to_address: Mapped[str | None] = mapped_column(String(128))
    value: Mapped[Decimal | None] = mapped_column(RawAmount)
    token_address: Mapped[str | None] = mapped_column(String(128))  # contract / mint; NULL = native
    token_symbol: Mapped[str | None] = mapped_column(String(32))
    token_decimals: Mapped[int | None] = mapped_column(Integer)
    fee: Mapped[Decimal | None] = mapped_column(RawAmount)  # native base units
    status: Mapped[str | None] = mapped_column(String(16))  # NULL = unknown
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Chain-specific extras that don't fit the common columns (normalized, not raw RPC dumps).
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
