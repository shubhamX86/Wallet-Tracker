from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.wallet import Wallet


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are normalized (lowercased) in the service layer; the DB enforces it.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)

    wallets: Mapped[list[Wallet]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
