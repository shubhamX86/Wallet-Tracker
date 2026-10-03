"""Chain-specific address validation/normalization (pure functions, no network calls).

Coverage: EVM (EIP-55), Solana (base58 32-byte key), Bitcoin MAINNET (base58check P2PKH/P2SH,
bech32 segwit v0, bech32m taproot v1+), Tron (base58check, 0x41 prefix), Sui (0x + 64 hex).
Validation proves an address is *well-formed*, not that it exists or has activity.
Bitcoin testnet/regtest addresses are rejected on purpose (mainnet only).
"""
from __future__ import annotations

import hashlib
import re

from eth_utils import is_checksum_address, to_checksum_address

from app.blockchain.base import InvalidAddressError
from app.chains.registry import CHAINS


class UnsupportedChainError(ValueError):
    pass


# ------------------------------------------------------------------ base58
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58)}


def b58decode(s: str) -> bytes:
    if not s:
        raise ValueError("empty")
    n = 0
    for ch in s:
        if ch not in _B58_INDEX:
            raise ValueError("invalid base58 character")
        n = n * 58 + _B58_INDEX[ch]
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + n.to_bytes((n.bit_length() + 7) // 8, "big")


def b58check_decode(s: str) -> bytes:
    """Return payload (version byte included) after verifying the 4-byte double-SHA256 checksum."""
    raw = b58decode(s)
    if len(raw) < 5:
        raise ValueError("too short")
    payload, checksum = raw[:-4], raw[-4:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
        raise ValueError("bad checksum")
    return payload


# ------------------------------------------------------------------ bech32 (BIP173/BIP350)
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32M_CONST = 0x2BC830A3


def _polymod(values: list[int]) -> int:
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk


def _bech32_decode(addr: str) -> tuple[str, list[int], str] | None:
    if addr != addr.lower() and addr != addr.upper():
        return None  # mixed case is invalid
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90:
        return None
    hrp = addr[:pos]
    data = [_CHARSET.find(c) for c in addr[pos + 1 :]]
    if -1 in data or any(ord(c) < 33 or ord(c) > 126 for c in hrp):
        return None
    const = _polymod([ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp] + data)
    if const == 1:
        return hrp, data[:-6], "bech32"
    if const == _BECH32M_CONST:
        return hrp, data[:-6], "bech32m"
    return None


def _convertbits(data: list[int], frombits: int, tobits: int) -> list[int] | None:
    acc = bits = 0
    out: list[int] = []
    maxv = (1 << tobits) - 1
    for v in data:
        acc = (acc << frombits) | v
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            out.append((acc >> bits) & maxv)
    if bits >= frombits or ((acc << (tobits - bits)) & maxv):  # non-zero padding
        return None
    return out


# ------------------------------------------------------------------ per-chain normalizers
_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SUI_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def normalize_evm_address(address: str) -> str:
    """Mixed-case input must satisfy EIP-55; all-lower/upper carries no checksum and is accepted."""
    if not isinstance(address, str) or not _EVM_RE.match(address):
        raise InvalidAddressError("Invalid EVM address format")
    body = address[2:]
    if body != body.lower() and body != body.upper() and not is_checksum_address(address):
        raise InvalidAddressError("Invalid EVM address checksum")
    return to_checksum_address(address)


def normalize_solana_address(address: str) -> str:
    if not isinstance(address, str) or not 32 <= len(address) <= 44:
        raise InvalidAddressError("Invalid Solana address")
    try:
        if len(b58decode(address)) != 32:
            raise ValueError
    except ValueError:
        raise InvalidAddressError("Invalid Solana address") from None
    return address


def normalize_bitcoin_address(address: str) -> str:
    if not isinstance(address, str) or not 14 <= len(address) <= 90:
        raise InvalidAddressError("Invalid Bitcoin address")
    if address[:3].lower() == "bc1":
        dec = _bech32_decode(address)
        if dec is None or dec[0] != "bc" or not dec[1]:
            raise InvalidAddressError("Invalid Bitcoin address")
        _, data, spec = dec
        version = data[0]
        program = _convertbits(data[1:], 5, 8)
        if version > 16 or program is None or not 2 <= len(program) <= 40:
            raise InvalidAddressError("Invalid Bitcoin address")
        if version == 0 and (spec != "bech32" or len(program) not in (20, 32)):
            raise InvalidAddressError("Invalid Bitcoin address")
        if version != 0 and spec != "bech32m":
            raise InvalidAddressError("Invalid Bitcoin address")
        return address.lower()
    try:
        payload = b58check_decode(address)
    except ValueError:
        raise InvalidAddressError("Invalid Bitcoin address") from None
    if len(payload) != 21 or payload[0] not in (0x00, 0x05):  # mainnet P2PKH / P2SH
        raise InvalidAddressError("Invalid Bitcoin address")
    return address


def normalize_tron_address(address: str) -> str:
    if not isinstance(address, str) or len(address) != 34:
        raise InvalidAddressError("Invalid Tron address")
    try:
        payload = b58check_decode(address)
    except ValueError:
        raise InvalidAddressError("Invalid Tron address") from None
    if len(payload) != 21 or payload[0] != 0x41:
        raise InvalidAddressError("Invalid Tron address")
    return address


def normalize_sui_address(address: str) -> str:
    if not isinstance(address, str) or not _SUI_RE.match(address):
        raise InvalidAddressError("Invalid Sui address")
    return address.lower()


_BY_FAMILY = {
    "evm": normalize_evm_address,
    "solana": normalize_solana_address,
    "bitcoin": normalize_bitcoin_address,
    "tron": normalize_tron_address,
    "sui": normalize_sui_address,
}
_FAMILY_OF = {c.id: c.family for c in CHAINS}


def supported_chain_ids() -> list[str]:
    return list(_FAMILY_OF)


def normalize_address(chain_id: str, address: str) -> str:
    """Canonical form of `address` for `chain_id`, or raise InvalidAddressError/UnsupportedChainError."""
    family = _FAMILY_OF.get(chain_id)
    if family is None:
        raise UnsupportedChainError(f"Unsupported chain '{chain_id}'")
    return _BY_FAMILY[family](address)
