"""Vocabulary shared by the classifier, the database CHECK constraints and the API.

Evidence strength is a *defined category*, not a calibrated probability:

- STRONG:   the label is read directly from the chain's own decoded data (e.g. a native `value`
            field, an ERC-20 Transfer log, a Solana System Program transfer). It proves the
            movement happened; it says nothing about the sender's intent.
- MODERATE: a registry-known protocol/entity identifier AND consistent balance changes agree.
- WEAK:     a single heuristic (e.g. only an address match, only a method selector).
- NONE:     only for UNKNOWN: evidence was insufficient. UNKNOWN is a valid, honest outcome.
"""
from enum import Enum


class TxLabel(str, Enum):
    NATIVE_TRANSFER = "native_transfer"
    TOKEN_TRANSFER = "token_transfer"
    SWAP = "swap"
    BRIDGE_TRANSFER = "bridge_transfer"
    EXCHANGE_DEPOSIT = "exchange_deposit"
    EXCHANGE_WITHDRAWAL = "exchange_withdrawal"
    CONTRACT_INTERACTION = "contract_interaction"
    LIQUIDITY_ADD = "liquidity_add"
    LIQUIDITY_REMOVE = "liquidity_remove"
    MINT = "mint"
    BURN = "burn"
    NFT_TRANSFER = "nft_transfer"
    UNKNOWN = "unknown"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class Basis(str, Enum):
    OBSERVED = "observed"  # a fact read from chain data
    INFERRED = "inferred"  # a label derived by heuristics / registries


def values(enum_cls: type[Enum]) -> list[str]:
    return [m.value for m in enum_cls]
