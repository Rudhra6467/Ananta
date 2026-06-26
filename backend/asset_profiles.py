"""
Asset-class profiles for the diversified 6-asset Kraken-native matrix.

Maps each symbol to a sector class and centralizes:
  - asset_class(symbol)        -> "L1" | "DEFI" | "METAL"
  - scan_interval(symbol)      -> cycles between Gemini evaluations (credit control)
  - exit_overrides(symbol)     -> per-class SL / trail param overrides (None => use global settings)
  - protocol_slug / chain_name -> DefiLlama lookups for sector grounding data

Rationale (ROADMAP §3 diversification): only PAXG (gold) is a true uncorrelated hedge;
BTC/ETH/SOL/LINK/AAVE are crypto-beta. Gold needs tight, low-volatility exit params so it can
actually react to 1-2% macro moves instead of being suffocated by crypto-tuned 10% stops.
"""
from __future__ import annotations

# symbol -> sector class
ASSET_CLASS: dict[str, str] = {
    "BTC/USD": "L1",
    "ETH/USD": "L1",
    "SOL/USD": "L1",
    "AVAX/USD": "L1",
    "XRP/USD": "L1",
    "LINK/USD": "DEFI",
    "AAVE/USD": "DEFI",
    "ARB/USD": "L2",
    "RENDER/USD": "AI",
    "PAXG/USD": "METAL",
}

# Gemini scan cadence in cycles. Majors every cycle; everything else every 3rd cycle (credit control).
SCAN_INTERVAL_BY_CLASS: dict[str, int] = {"L1": 1, "DEFI": 3, "L2": 3, "AI": 3, "METAL": 3}

# Per-class exit-parameter overrides. Absent fields fall back to global RiskSettings.
# METAL (gold) gets tight, low-vol params so 1-2% macro shifts can trigger entries/exits.
CLASS_EXIT_OVERRIDES: dict[str, dict] = {
    "METAL": {
        "stop_loss_pct": 2.5,
        "trail_arm_pct": 1.0,
        "trail_distance_pct": 0.7,
        "dynamic_trail_min_pct": 0.3,
        "dynamic_trail_max_pct": 1.5,
    },
}

# DefiLlama protocol slug for DeFi tokens (TVL grounding).
PROTOCOL_SLUG: dict[str, str] = {"AAVE/USD": "aave", "LINK/USD": "chainlink"}

# DefiLlama chain name for L1/L2 tokens (chain TVL grounding). RENDER (AI) has no
# chain TVL — it leans on AI-sector macro feeds instead.
CHAIN_NAME: dict[str, str] = {
    "BTC/USD": "Bitcoin", "ETH/USD": "Ethereum", "SOL/USD": "Solana",
    "AVAX/USD": "Avalanche", "XRP/USD": "Ripple", "ARB/USD": "Arbitrum",
}

DEFAULT_ASSETS: list[str] = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "XRP/USD", "PAXG/USD",
    "LINK/USD", "AAVE/USD", "ARB/USD", "RENDER/USD",
]
# Backward-compat alias (legacy import name).
DEFAULT_SIX_ASSETS = DEFAULT_ASSETS


def asset_class(symbol: str) -> str:
    return ASSET_CLASS.get(symbol, "L1")


def scan_interval(symbol: str) -> int:
    return SCAN_INTERVAL_BY_CLASS.get(asset_class(symbol), 1)


def exit_overrides(symbol: str) -> dict:
    return CLASS_EXIT_OVERRIDES.get(asset_class(symbol), {})


def eff_setting(settings, symbol: str, field: str):
    """Effective value for an exit param: per-class override if present, else the global setting."""
    return exit_overrides(symbol).get(field, getattr(settings, field))


def protocol_slug(symbol: str) -> str | None:
    return PROTOCOL_SLUG.get(symbol)


def chain_name(symbol: str) -> str | None:
    return CHAIN_NAME.get(symbol)
