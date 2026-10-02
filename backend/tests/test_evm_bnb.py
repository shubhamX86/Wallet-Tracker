import os
from decimal import Decimal

import httpx
import pytest

from app.blockchain.base import (
    BlockchainAdapter, DataNotFoundError, InvalidAddressError, ProviderResponseError, TxStatus,
)
from app.blockchain.evm import EVM_SPECS, EvmAdapter, create_evm_adapter
from app.blockchain.rpc import JsonRpcClient
from app.core.config import Settings

CHECKSUMMED = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"  # EIP-55 reference vector
LOWER = CHECKSUMMED.lower()
OWNER = "0x" + "11" * 20
TOKEN = "0x" + "22" * 20
TX = "0x" + "ab" * 32


async def _nosleep(_):
    pass


class FakeNode:
    """Mock JSON-RPC node. `results` maps method -> result (or callable(params))."""

    def __init__(self, chain_id=56, **results):
        self.calls: list[tuple[str, list]] = []
        self.results = {"eth_chainId": hex(chain_id), "eth_blockNumber": hex(1000), **results}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        self.calls.append((body["method"], body["params"]))
        res = self.results[body["method"]]
        res = res(body["params"]) if callable(res) else res
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": res})

    def count(self, method=None):
        return len([c for c in self.calls if method is None or c[0] == method])


def adapter(node, max_retries=0) -> EvmAdapter:
    rpc = JsonRpcClient(
        "https://node.example.com/KEY", label="bsc", transport=httpx.MockTransport(node),
        sleep=_nosleep, max_retries=max_retries,
    )
    return EvmAdapter(EVM_SPECS["bsc"], rpc)


# ---------------------------------------------------------------- spec / config
def test_bnb_spec_metadata():
    s = EVM_SPECS["bsc"]
    assert (s.evm_chain_id, s.native_symbol, s.native_decimals) == (56, "BNB", 18)


def test_factory_reads_url_from_settings_and_rejects_unknown_chain():
    a = create_evm_adapter("bsc", Settings(bnb_rpc_url="https://rpc.example/x"))
    assert isinstance(a, BlockchainAdapter) and a.native_symbol == "BNB"
    with pytest.raises(ValueError):
        create_evm_adapter("solana", Settings())


# ---------------------------------------------------------------- address validation
def test_valid_addresses_normalize_to_checksum():
    a = adapter(FakeNode())
    assert a.normalize_address(CHECKSUMMED) == CHECKSUMMED
    assert a.normalize_address(LOWER) == CHECKSUMMED
    assert a.normalize_address("0x" + LOWER[2:].upper()) == CHECKSUMMED  # all-upper: no checksum claimed


@pytest.mark.parametrize(
    "bad",
    [
        "0x" + CHECKSUMMED[2:].swapcase(),  # mixed case with a broken EIP-55 checksum
        "0x" + "g" * 40,
        "0x1234",
        LOWER[2:],  # missing 0x
        "0X" + LOWER[2:],
        CHECKSUMMED + "00",
        "",
        "TJRabPrwbZy45sbavfcjinPJC18kjpRTv8",  # Tron address is not EVM
        "So11111111111111111111111111111111111111112",  # Solana
        None,
        12345,
    ],
)
def test_invalid_addresses_rejected(bad):
    a = adapter(FakeNode())
    with pytest.raises(InvalidAddressError):
        a.normalize_address(bad)
    assert not a.is_valid_address(bad)


# ---------------------------------------------------------------- health
async def test_health_ok():
    h = await adapter(FakeNode()).health()
    assert h.ok and h.latest_block == 1000 and h.chain == "bsc" and h.error is None


async def test_health_reports_wrong_network_instead_of_ok():
    h = await adapter(FakeNode(chain_id=1)).health()  # endpoint actually serves Ethereum
    assert not h.ok and "chain id mismatch" in h.error


async def test_health_never_raises_when_provider_down():
    def down(_):
        raise httpx.ConnectError("refused")

    h = await adapter(down).health()
    assert not h.ok and h.latest_block is None and "unreachable" in h.error
    assert "example.com" not in h.error and "KEY" not in h.error


# ---------------------------------------------------------------- native balance
async def test_native_balance_conversion():
    node = FakeNode(eth_getBalance=hex(15 * 10**17))
    b = await adapter(node).get_native_balance(LOWER)
    assert b.amount == Decimal("1.5") and b.symbol == "BNB" and b.address == CHECKSUMMED
    assert node.calls[-1] == ("eth_getBalance", [CHECKSUMMED, "latest"])


async def test_zero_balance_is_zero_not_missing():
    b = await adapter(FakeNode(eth_getBalance="0x0")).get_native_balance(LOWER)
    assert b.raw == 0 and b.amount == Decimal("0")


async def test_invalid_address_never_hits_the_provider():
    node = FakeNode()
    with pytest.raises(InvalidAddressError):
        await adapter(node).get_native_balance("nope")
    assert node.count() == 0


async def test_wrong_network_blocks_balance_queries():
    with pytest.raises(ProviderResponseError, match="chain id mismatch"):
        await adapter(FakeNode(chain_id=1, eth_getBalance="0x1")).get_native_balance(LOWER)


async def test_malformed_balance_rejected():
    with pytest.raises(ProviderResponseError):
        await adapter(FakeNode(eth_getBalance="not-hex")).get_native_balance(LOWER)


async def test_network_identity_checked_once():
    node = FakeNode(eth_getBalance="0x1")
    a = adapter(node)
    await a.get_native_balance(LOWER)
    await a.get_native_balance(LOWER)
    assert node.count("eth_chainId") == 1


# ---------------------------------------------------------------- tokens
def _token_node(decimals_result):
    def eth_call(params):
        data = params[0]["data"]
        if data.startswith("0x70a08231"):
            assert data.endswith(OWNER[2:]) and len(data) == 10 + 64
            return hex(2_500_000)
        return decimals_result(data)

    return FakeNode(eth_call=eth_call)


async def test_token_balance_with_decimals():
    t = await adapter(_token_node(lambda d: hex(6))).get_token_balance(OWNER, TOKEN)
    assert t.raw == 2_500_000 and t.decimals == 6 and t.amount == Decimal("2.5")
    assert t.token_address == adapter(FakeNode()).normalize_address(TOKEN)


async def test_token_decimals_unavailable_is_none_not_guessed():
    node =_token_node(lambda d: "0x")  # contract without decimals() returns empty data
    t = await adapter(node).get_token_balance(OWNER, TOKEN)
    assert t.decimals is None and t.amount is None and t.raw == 2_500_000


# ---------------------------------------------------------------- transactions
def _tx_node(status="0x1", mined=True, receipt=True):
    tx = {
        "hash": TX, "from": LOWER, "to": OWNER, "value": hex(10**18),
        "blockNumber": hex(990) if mined else None,
    }
    rec = {"status": status, "gasUsed": hex(21000), "effectiveGasPrice": hex(5 * 10**9)} if receipt else None
    return FakeNode(
        eth_getTransactionByHash=tx,
        eth_getTransactionReceipt=rec,
        eth_getBlockByNumber={"timestamp": hex(1_700_000_000)},
    )


async def test_transaction_success_fields():
    t = await adapter(_tx_node()).get_transaction(TX.upper().replace("0X", "0x"))
    assert t.tx_id == TX and t.chain == "bsc"
    assert t.block == 990 and t.confirmations == 11
    assert t.sender == CHECKSUMMED and t.recipient == adapter(FakeNode()).normalize_address(OWNER)
    assert t.value_raw == 10**18 and t.fee_raw == 21000 * 5 * 10**9
    assert t.status is TxStatus.SUCCESS and t.timestamp.year == 2023


async def test_transaction_failed_status():
    assert (await adapter(_tx_node(status="0x0")).get_transaction(TX)).status is TxStatus.FAILED


async def test_pending_transaction_leaves_unknowns_as_none():
    t = await adapter(_tx_node(mined=False, receipt=False)).get_transaction(TX)
    assert t.block is None and t.status is None and t.timestamp is None
    assert t.fee_raw is None and t.confirmations is None and t.value_raw == 10**18


async def test_unknown_transaction_is_not_found():
    with pytest.raises(DataNotFoundError):
        await adapter(FakeNode(eth_getTransactionByHash=None)).get_transaction(TX)


@pytest.mark.parametrize("bad", ["0x1234", "x" * 66, LOWER, ""])
async def test_invalid_tx_hash_rejected(bad):
    with pytest.raises(InvalidAddressError):
        await adapter(FakeNode()).get_transaction(bad)


# ---------------------------------------------------------------- optional live test
@pytest.mark.skipif(os.getenv("RUN_LIVE_RPC") != "1", reason="set RUN_LIVE_RPC=1 to hit the real BNB RPC")
async def test_live_bnb_readonly_connectivity():
    a = create_evm_adapter("bsc", Settings())
    try:
        h = await a.health()
        assert h.ok, h.error
        assert h.latest_block > 40_000_000
    finally:
        await a.aclose()
