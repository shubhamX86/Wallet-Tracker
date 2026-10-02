"""Static network registry (configuration, not live data).

`status` states what is actually implemented. Nothing here is "live" until its
adapter exists; Phase 3 flips ethereum/solana, Phase 5 the remaining EVM chains.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ChainInfo:
    id: str
    name: str
    family: str  # "evm" | "solana" | "bitcoin" | "tron" | "sui"
    native_symbol: str
    evm_chain_id: int | None
    status: str  # "planned" | "adapter_ready" | "live"
    planned_phase: int


CHAINS: tuple[ChainInfo, ...] = (
    ChainInfo("ethereum", "Ethereum", "evm", "ETH", 1, "planned", 3),
    ChainInfo("solana", "Solana", "solana", "SOL", None, "planned", 3),
    ChainInfo("bsc", "BNB Chain", "evm", "BNB", 56, "planned", 5),
    ChainInfo("base", "Base", "evm", "ETH", 8453, "planned", 5),
    ChainInfo("arbitrum", "Arbitrum", "evm", "ETH", 42161, "planned", 5),
    ChainInfo("optimism", "Optimism", "evm", "ETH", 10, "planned", 5),
    ChainInfo("polygon", "Polygon", "evm", "POL", 137, "planned", 5),
    ChainInfo("avalanche", "Avalanche C-Chain", "evm", "AVAX", 43114, "planned", 5),
    ChainInfo("bitcoin", "Bitcoin", "bitcoin", "BTC", None, "planned", 5),
    ChainInfo("tron", "Tron", "tron", "TRX", None, "planned", 5),
    ChainInfo("sui", "Sui", "sui", "SUI", None, "planned", 5),
)
