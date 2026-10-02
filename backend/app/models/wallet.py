from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Wallet(TimestampMixin, Base):
    """A public address a user watches. Read-only: no keys or seed phrases, ever."""

    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "chain", "address", name="uq_wallets_user_chain_address"),
        Index("ix_wallets_user_id_chain", "user_id", "chain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="wallets")
