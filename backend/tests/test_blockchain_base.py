from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.blockchain.base import (
    BlockchainAdapter, BlockchainError, DataNotFoundError, InvalidAddressError,
    NativeBalance, ProviderResponseError, ProviderUnavailableError, RateLimitedError,
    TokenBalance, units_from_raw,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_wei_to_eth_exact():
    assert units_from_raw(10**18, 18) == Decimal("1")
    assert units_from_raw(1, 18) == Decimal("0.000000000000000001")  # no float rounding
    assert units_from_raw(1_500_000_000, 9) == Decimal("1.5")  # lamports -> SOL
    assert units_from_raw(0, 18) == Decimal("0")


def test_units_reject_negative():
    with pytest.raises(ValueError):
        units_from_raw(-1, 18)


def test_native_balance_amount():
    b = NativeBalance("ethereum", "0xabc", "ETH", 2 * 10**18, 18, NOW)
    assert b.amount == Decimal("2")


def test_token_balance_unknown_decimals_is_none_not_zero():
    unknown = TokenBalance("ethereum", "0xo", "0xt", 5, None, NOW)
    zero = TokenBalance("ethereum", "0xo", "0xt", 0, 6, NOW)
    assert unknown.amount is None
    assert zero.amount == Decimal("0")


def test_retryable_flags():
    assert ProviderUnavailableError("x").retryable
    assert RateLimitedError("x").retryable
    for cls in (InvalidAddressError, DataNotFoundError, ProviderResponseError):
        assert not cls("x").retryable
    assert issubclass(RateLimitedError, BlockchainError)


def test_interface_cannot_be_instantiated_incomplete():
    with pytest.raises(TypeError):
        BlockchainAdapter()  # type: ignore[abstract]

    class Partial(BlockchainAdapter):
        chain_id = "x"
        native_symbol = "X"
        native_decimals = 0

        def normalize_address(self, address: str) -> str:
            return address

    with pytest.raises(TypeError):
        Partial()  # type: ignore[abstract]


def test_interface_has_no_write_or_key_methods():
    names = {n.lower() for n in dir(BlockchainAdapter)}
    assert not {n for n in names if any(w in n for w in ("sign", "send", "private", "seed", "mnemonic"))}


def test_is_valid_address_uses_normalize():
    class Fake(BlockchainAdapter):
        chain_id, native_symbol, native_decimals = "fake", "F", 0

        def normalize_address(self, address: str) -> str:
            if not address.startswith("ok"):
                raise InvalidAddressError("bad address")
            return address

        async def health(self): ...
        async def get_native_balance(self, address): ...
        async def get_token_balance(self, owner, token_address): ...
        async def get_transaction(self, tx_id): ...
        async def aclose(self): ...

    f = Fake()
    assert f.is_valid_address("ok1") and not f.is_valid_address("nope")
