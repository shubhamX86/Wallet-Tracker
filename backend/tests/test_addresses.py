"""Address validators, using published reference vectors (BIP173/BIP350, EIP-55, known mainnet addresses)."""
import pytest

from app.blockchain.addresses import UnsupportedChainError, normalize_address, supported_chain_ids
from app.blockchain.base import InvalidAddressError
from app.chains.registry import CHAINS

EIP55 = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
BTC_P2PKH = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"  # genesis block address
BTC_P2SH = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
BTC_P2WPKH = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"  # BIP173
BTC_P2WSH = "bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3"  # BIP173
BTC_TAPROOT = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"  # BIP350
TRON_USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
SOL_WSOL = "So11111111111111111111111111111111111111112"
SOL_SYSTEM = "11111111111111111111111111111111"
SUI = "0x" + "ab" * 32

EVM_CHAINS = ["ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"]


def test_every_registry_chain_is_supported():
    assert set(supported_chain_ids()) == {c.id for c in CHAINS} and len(CHAINS) == 11


@pytest.mark.parametrize("chain", EVM_CHAINS)
def test_evm_chains_share_eip55_rules(chain):
    assert normalize_address(chain, EIP55.lower()) == EIP55
    assert normalize_address(chain, EIP55) == EIP55
    with pytest.raises(InvalidAddressError):
        normalize_address(chain, "0x" + EIP55[2:].swapcase())  # broken checksum


@pytest.mark.parametrize(
    "chain,address",
    [
        ("bitcoin", BTC_P2PKH), ("bitcoin", BTC_P2SH), ("bitcoin", BTC_P2WPKH),
        ("bitcoin", BTC_P2WSH), ("bitcoin", BTC_TAPROOT),
        ("tron", TRON_USDT), ("solana", SOL_WSOL), ("solana", SOL_SYSTEM), ("sui", SUI),
    ],
)
def test_valid_reference_addresses(chain, address):
    assert normalize_address(chain, address).lower() == address.lower()


def test_bech32_uppercase_is_normalized_but_mixed_case_rejected():
    assert normalize_address("bitcoin", BTC_P2WPKH.upper()) == BTC_P2WPKH
    mixed = BTC_P2WPKH[:10] + BTC_P2WPKH[10:].upper()
    with pytest.raises(InvalidAddressError):
        normalize_address("bitcoin", mixed)


def test_sui_normalized_to_lowercase():
    assert normalize_address("sui", "0x" + "AB" * 32) == SUI


@pytest.mark.parametrize(
    "chain,address",
    [
        ("bitcoin", BTC_P2PKH[:-1] + "b"),  # base58check checksum broken
        ("bitcoin", BTC_P2WPKH[:-1] + "p"),  # bech32 checksum broken
        ("bitcoin", "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"),  # testnet rejected on purpose
        ("bitcoin", BTC_TAPROOT[:-1] + "q"),
        ("bitcoin", EIP55),
        ("bitcoin", ""),
        ("tron", TRON_USDT[:-1] + "u"),
        ("tron", BTC_P2PKH),  # valid base58check but wrong version byte / length
        ("tron", EIP55),
        ("solana", "0OIl" + "1" * 30),  # characters outside the base58 alphabet
        ("solana", "abc"),
        ("solana", SOL_WSOL + "1"),  # decodes to != 32 bytes
        ("solana", EIP55),
        ("sui", "0x2"),
        ("sui", "0x" + "ab" * 31),
        ("sui", "0x" + "zz" * 32),
        ("sui", EIP55),
        ("ethereum", TRON_USDT),
        ("ethereum", SOL_WSOL),
        ("ethereum", SUI),
        ("ethereum", BTC_P2WPKH),
        ("ethereum", ""),
        ("ethereum", None),
        ("bsc", 12345),
    ],
)
def test_invalid_addresses_rejected(chain, address):
    with pytest.raises(InvalidAddressError):
        normalize_address(chain, address)


def test_unsupported_chain():
    with pytest.raises(UnsupportedChainError):
        normalize_address("dogecoin", "D8vFz4p1L37jdg47HXKtbjnCd5hzUm6yNd")
