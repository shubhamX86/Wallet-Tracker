"""Generic read-only adapter for EVM chains, parameterised by an EvmChainSpec.

Only standard JSON-RPC is used. NOTE: standard RPC cannot list "all transactions of an
address"; historical wallet activity needs an indexer/explorer API (a later step). This
adapter covers balances, token balances and single-transaction lookups.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from eth_utils import is_checksum_address, to_checksum_address

from app.blockchain.base import (
    BlockchainAdapter, BlockchainError, DataNotFoundError, InvalidAddressError, NativeBalance,
    ProviderHealth, ProviderResponseError, TokenBalance, TransactionInfo, TxStatus,
)
from app.blockchain.rpc import JsonRpcClient
from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("whale.evm")

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_BALANCE_OF = "0x70a08231"  # balanceOf(address)
_DECIMALS = "0x313ce567"  # decimals()


@dataclass(frozen=True)
class EvmChainSpec:
    chain_id: str  # matches app.chains.registry
    name: str
    evm_chain_id: int
    native_symbol: str
    native_decimals: int
    rpc_setting: str  # attribute name on Settings holding the RPC URL


EVM_SPECS: dict[str, EvmChainSpec] = {
    "bsc": EvmChainSpec("bsc", "BNB Chain", 56, "BNB", 18, "bnb_rpc_url"),
}


def _to_int(value: object, what: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ProviderResponseError(f"Provider returned an invalid {what}")
    try:
        return int(value, 16)
    except ValueError:
        raise ProviderResponseError(f"Provider returned an invalid {what}") from None


def _checksum_or_none(value: object) -> str | None:
    if isinstance(value, str) and _ADDR_RE.match(value):
        return to_checksum_address(value)
    return None


class EvmAdapter(BlockchainAdapter):
    def __init__(self, spec: EvmChainSpec, rpc: JsonRpcClient):
        self.spec = spec
        self.chain_id = spec.chain_id
        self.native_symbol = spec.native_symbol
        self.native_decimals = spec.native_decimals
        self._rpc = rpc
        self._network_verified = False

    # ------------------------------------------------------------ validation
    def normalize_address(self, address: str) -> str:
        """0x + 40 hex. Mixed-case input must satisfy EIP-55; all-lower/upper carries no
        checksum and is accepted. Always returns the EIP-55 checksummed form."""
        if not isinstance(address, str) or not _ADDR_RE.match(address):
            raise InvalidAddressError("Invalid EVM address format")
        body = address[2:]
        if body != body.lower() and body != body.upper() and not is_checksum_address(address):
            raise InvalidAddressError("Invalid EVM address checksum")
        return to_checksum_address(address)

    @staticmethod
    def normalize_tx_hash(tx_id: str) -> str:
        if not isinstance(tx_id, str) or not _TX_RE.match(tx_id):
            raise InvalidAddressError("Invalid EVM transaction hash")
        return tx_id.lower()

    # ------------------------------------------------------------ internals
    async def _ensure_network(self) -> None:
        """Refuse to answer if the endpoint serves a different network than configured."""
        if self._network_verified:
            return
        served = _to_int(await self._rpc.call("eth_chainId"), "chain id")
        if served != self.spec.evm_chain_id:
            raise ProviderResponseError(
                f"Configured provider is not serving {self.spec.name} (chain id mismatch)"
            )
        self._network_verified = True

    # ------------------------------------------------------------ interface
    async def health(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            await self._ensure_network()
            block = _to_int(await self._rpc.call("eth_blockNumber"), "block number")
        except BlockchainError as exc:
            return ProviderHealth(self.chain_id, False, None, None, exc.message)
        ms = round((time.perf_counter() - start) * 1000, 1)
        return ProviderHealth(self.chain_id, True, block, ms)

    async def get_native_balance(self, address: str) -> NativeBalance:
        addr = self.normalize_address(address)
        await self._ensure_network()
        raw = _to_int(await self._rpc.call("eth_getBalance", [addr, "latest"]), "balance")
        return NativeBalance(
            self.chain_id, addr, self.native_symbol, raw, self.native_decimals, datetime.now(timezone.utc)
        )

    async def get_token_balance(self, owner: str, token_address: str) -> TokenBalance:
        owner_n = self.normalize_address(owner)
        token_n = self.normalize_address(token_address)
        await self._ensure_network()
        data = _BALANCE_OF + owner_n[2:].lower().rjust(64, "0")
        raw = _to_int(
            await self._rpc.call("eth_call", [{"to": token_n, "data": data}, "latest"]), "token balance"
        )
        decimals: int | None
        try:
            decimals = _to_int(
                await self._rpc.call("eth_call", [{"to": token_n, "data": _DECIMALS}, "latest"]), "decimals"
            )
        except BlockchainError:
            decimals = None  # unknown: surfaced as None, never guessed
        return TokenBalance(self.chain_id, owner_n, token_n, raw, decimals, datetime.now(timezone.utc))

    async def get_transaction(self, tx_id: str) -> TransactionInfo:
        tx_hash = self.normalize_tx_hash(tx_id)
        await self._ensure_network()
        tx = await self._rpc.call("eth_getTransactionByHash", [tx_hash])
        if tx is None:
            raise DataNotFoundError("Transaction not found on this provider")
        if not isinstance(tx, dict):
            raise ProviderResponseError("Provider returned an invalid transaction")

        receipt = await self._rpc.call("eth_getTransactionReceipt", [tx_hash])  # None while pending
        block = _to_int(tx["blockNumber"], "block number") if tx.get("blockNumber") else None

        status = None
        fee = None
        if isinstance(receipt, dict):
            if receipt.get("status") in ("0x1", "0x0"):
                status = TxStatus.SUCCESS if receipt["status"] == "0x1" else TxStatus.FAILED
            if receipt.get("gasUsed") and receipt.get("effectiveGasPrice"):
                fee = _to_int(receipt["gasUsed"], "gas used") * _to_int(
                    receipt["effectiveGasPrice"], "gas price"
                )

        timestamp = None
        confirmations = None
        if block is not None:
            try:
                header = await self._rpc.call("eth_getBlockByNumber", [hex(block), False])
                if isinstance(header, dict) and header.get("timestamp"):
                    timestamp = datetime.fromtimestamp(_to_int(header["timestamp"], "timestamp"), timezone.utc)
                latest = _to_int(await self._rpc.call("eth_blockNumber"), "block number")
                confirmations = max(0, latest - block + 1)
            except BlockchainError as exc:
                log.warning("evm_tx_enrichment_failed", chain=self.chain_id, reason=exc.message)

        return TransactionInfo(
            chain=self.chain_id,
            tx_id=tx_hash,
            block=block,
            timestamp=timestamp,
            sender=_checksum_or_none(tx.get("from")),
            recipient=_checksum_or_none(tx.get("to")),  # None for contract creation
            value_raw=_to_int(tx["value"], "value") if tx.get("value") is not None else None,
            fee_raw=fee,
            status=status,
            confirmations=confirmations,
        )

    async def aclose(self) -> None:
        await self._rpc.aclose()


def create_evm_adapter(chain_id: str, settings: Settings, **rpc_kwargs) -> EvmAdapter:
    try:
        spec = EVM_SPECS[chain_id]
    except KeyError:
        raise ValueError(f"No EVM adapter configured for chain '{chain_id}'") from None
    rpc = JsonRpcClient(
        getattr(settings, spec.rpc_setting),
        label=chain_id,
        timeout=settings.rpc_timeout_seconds,
        max_retries=settings.rpc_max_retries,
        **rpc_kwargs,
    )
    return EvmAdapter(spec, rpc)
