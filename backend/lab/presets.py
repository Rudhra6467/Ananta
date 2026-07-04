"""
lab/presets.py — WS3 Mode C: named parameter presets for one-click validation.

Each preset is a bundle of RiskSettings overrides representing a coherent trading
"personality". The Lab runs a backtest with the preset's overrides so the operator
can compare canned strategies against the live production config without hand-tuning.
"""
from __future__ import annotations

PRESETS: list[dict] = [
    {
        "id": "conservative",
        "label": "Conservative Capital-Preservation",
        "description": "Tighter stops, stricter oversold entries, earlier profit lock. Fewer, higher-quality trades.",
        "setting_overrides": {
            "stop_loss_pct": 8.0,
            "rsi_reset_min": 30.0,
            "rsi_reset_max": 33.0,
            "vol_exhaustion_ratio_max": 0.5,
            "vcp_enabled": True,
            "cont_pullback_max_pct": 8.0,
        },
    },
    {
        "id": "aggressive",
        "label": "Aggressive Momentum",
        "description": "Looser entry gates and wider ATR demand zone — more trades, accepts higher drawdown for reach.",
        "setting_overrides": {
            "stop_loss_pct": 12.0,
            "rsi_reset_min": 28.0,
            "rsi_reset_max": 40.0,
            "atr_zone_above_mult": 0.8,
            "vol_exhaustion_ratio_max": 0.75,
            "vcp_enabled": False,
            "cont_rsi_max": 68.0,
            "cont_pullback_max_pct": 15.0,
        },
    },
    {
        "id": "high_volatility",
        "label": "High-Volatility Regime",
        "description": "Wider stops and ATR zones tuned for volatile assets; squeeze needs stronger breakout volume.",
        "setting_overrides": {
            "stop_loss_pct": 14.0,
            "atr_zone_above_mult": 0.9,
            "atr_zone_below_mult": 0.5,
            "squeeze_vol_expansion_min": 1.8,
            "cont_support_atr_mult": 0.9,
        },
    },
    {
        "id": "reversal_purist",
        "label": "Reversal Purist (Hunter-only)",
        "description": "Disables continuation; strict VCP + narrow 30-34 RSI band. Pure 'buy fear' mean-reversion.",
        "setting_overrides": {
            "rsi_reset_min": 30.0,
            "rsi_reset_max": 34.0,
            "vcp_enabled": True,
            "vol_exhaustion_ratio_max": 0.55,
            "continuation_enabled": False,
        },
    },
]

_BY_ID = {p["id"]: p for p in PRESETS}


def get_preset(preset_id: str) -> dict | None:
    return _BY_ID.get(preset_id)
