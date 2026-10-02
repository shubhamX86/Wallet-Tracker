"""Common read-only interface for chain adapters.

Design rules:
- Adapters only READ public data. There is no method that signs or sends anything,
  and none accepts key material.
- Amounts are exact: raw integer units + decimals -> Decimal. Never float.
- "Unknown/unavailable" is expressed as ``None`` (or a DataNotFoundError), never as 0,
  so a genuine zero balance is distinguishable from missing data.
- Errors carry a short safe message only: never provider URLs, API keys or raw payloads.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ---------------------------------------------------------------- errors
class BlockchainError(Exception):
    """Base error. ``retryable`` tells the retry layer (Phase 3 Step 9) whether to retry."""

    retryable: bool = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidAddressError(BlockchainError):
    """Malformed address / identifier supplied by the caller. Never retried."""


class DataNotFoundError(BlockchainError):
    """Provider answered, but the object (e.g. transaction) is not available/indexed."""


class ProviderUnavailableError(BlockchainError):
    """Timeout or connection failure."""

    retryable = True


class RateLimitedError(BlockchainError):
    """Provider returned a rate-limit response."""

    retryable = True


class ProviderResponseError(BlockchainError):
    """Malformed or unexpected provider response."""


# ---------------------------------------------------------------- helpers
def units_from_raw(raw: int, decimals: int) -> Decimal:
    """Exact conversion, e.g. wei -> ETH (decimals=18), lamports -> SOL (decimals=9)."""
    if raw < 0 or decimals < 0:
        raise ValueError("raw and decimals must be non-negative")
    return Decimal(raw).scaleb(-decimals)


# ---------------------------------------------------------------- result types
class TxStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class ProviderHealth:
    chain: str
    ok: bool
    latest_block: int | None  # block number (EVM) or slot (Solana); None if unreachable
    latency_ms: float | None
    error: str | None = None  # short safe message


@dataclass(frozen=True)
class NativeBalance:
    chain: str
    address: str  # normalized form
    symbol: str
    raw: int
    decimals: int
    retrieved_at: datetime

    @property
    def amount(self) -> Decimal:
        return units_from_raw(self.raw, self.decimals)


@dataclass(frozen=True)
class TokenBalance:
    chain: str
    owner: str
    token_address: str  # contract (EVM) or mint (Solana)
    raw: int
    decimals: int | None  # None if the provider did not report it
    retrieved_at: datetime

    @property
    def amount(self) -> Decimal | None:
        return None if self.decimals is None else units_from_raw(self.raw, self.decimals)


@dataclass(frozen=True)
class TransactionInfo:
    """Every optional field is None when the provider did not supply it."""

    chain: str
    tx_id: str
    block: int | None = None  # block number or slot
    timestamp: datetime | None = None
    sender: str | None = None
    recipient: str | None = None
    value_raw: int | None = None  # native units
    fee_raw: int | None = None
    status: TxStatus | None = None  # None = unknown/pending
    confirmations: int | None = None


# ---------------------------------------------------------------- interface
class BlockchainAdapter(ABC):
    chain_id: str  # matches app.chains.registry
    native_symbol: str
    native_decimals: int

    @abstractmethod
    def normalize_address(self, address: str) -> str:
        """Return the canonical form or raise InvalidAddressError."""

    def is_valid_address(self, address: str) -> bool:
        try:
            self.normalize_address(address)
            return True
        except InvalidAddressError:
            return False

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Never raises for provider failure; reports ok=False instead."""

    @abstractmethod
    async def get_native_balance(self, address: str) -> NativeBalance: ...

    @abstractmethod
    async def get_token_balance(self, owner: str, token_address: str) -> TokenBalance: ...

    @abstractmethod
    async def get_transaction(self, tx_id: str) -> TransactionInfo:
        """Raise DataNotFoundError if the provider has no such transaction."""

    @abstractmethod
    async def aclose(self) -> None: ...
