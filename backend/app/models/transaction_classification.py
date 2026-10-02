from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Integer

from app.classification.types import Basis, EvidenceStrength, TxLabel, values
from app.db.base import Base, TimestampMixin


def _in(column: str, enum_cls) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values(enum_cls))})"


class TransactionClassification(TimestampMixin, Base):
    """What we concluded about one on-chain transaction, for one tracked wallet, and why.

    One row per (wallet, chain, tx_hash, rule_version): re-running the same rule version is an
    upsert; a new rule version adds a new row so earlier conclusions stay auditable.
    `transfer_indexes` lists which rows of `transactions` (by transfer_index) the label covers.
    Classification refers to ingested data only; it never calls a node.
    """

    __tablename__ = "transaction_classifications"
    __table_args__ = (
        UniqueConstraint(
            "wallet_id", "chain", "tx_hash", "rule_version", name="uq_tx_class_wallet_chain_hash_version"
        ),
        CheckConstraint(_in("label", TxLabel), name="label_valid"),
        CheckConstraint(_in("evidence_strength", EvidenceStrength), name="strength_valid"),
        CheckConstraint(_in("basis", Basis), name="basis_valid"),
        # Unknown must say "no evidence"; every real label must carry some evidence.
        CheckConstraint(
            "(label = 'unknown') = (evidence_strength = 'none')", name="unknown_iff_no_evidence"
        ),
        Index("ix_tx_class_wallet_id_tx_timestamp", "wallet_id", "tx_timestamp"),
        Index("ix_tx_class_label", "label"),
        Index("ix_tx_class_chain_tx_hash", "chain", "tx_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    transfer_indexes: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'")
    )

    label: Mapped[str] = mapped_column(String(32), nullable=False)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(16), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Structured, human-auditable items, e.g. {"type": "erc20_transfer_log", "log_index": 3, ...}
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Detected assets/amounts as raw base units + token identity (never floats).
    assets: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Missing-data / ambiguity notes, e.g. ["receipt unavailable", "router not in registry"].
    uncertainty_notes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    tx_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
