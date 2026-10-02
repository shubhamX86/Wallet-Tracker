from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SyncCheckpoint(TimestampMixin, Base):
    """Per-wallet ingestion progress (one row per wallet).

    Advanced only in the same DB transaction that persists the transactions it covers, so a
    crash can never skip data. `error` must already be redacted (no URLs / API keys).
    """

    __tablename__ = "sync_checkpoints"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'syncing', 'synced', 'error')", name="status_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    last_block: Mapped[int | None] = mapped_column(BigInteger)  # last processed block / slot
    cursor: Mapped[str | None] = mapped_column(String(128))  # latest tx signature / page cursor
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
