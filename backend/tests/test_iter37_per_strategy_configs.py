"""P3 per-strategy engine config resolution — unit tests (no network, no LLM).

Covers strategy_runtime.overlay_settings + resolve_active_params, incl. the
account-level split (per-strategy configs must never override account-level risk).
"""
from __future__ import annotations

import pytest

import strategy.definitions  # noqa: F401  (registers schemas)
import strategy_runtime as sr
from models import RiskSettings


# ---- fake async mongo (just enough for resolve_active_params) ----
class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _n):
        return list(self._docs)


class _Coll:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query=None, projection=None):
        query = query or {}
        docs = self._docs
        # support the {"active_config_id": {"$ne": None}} filter used by the resolver
        acid = query.get("active_config_id")
        if isinstance(acid, dict) and "$ne" in acid:
            docs = [d for d in docs if d.get("active_config_id") is not None]
        return _Cursor(docs)


class _DB:
    def __init__(self, metas, configs):
        self.strategy_meta = _Coll(metas)
        self.strategy_configs = _Coll(configs)


def test_overlay_noop_when_empty():
    s = RiskSettings()
    assert sr.overlay_settings(s, None) is s
    assert sr.overlay_settings(s, {}) is s


def test_overlay_applies_strategy_level_field():
    s = RiskSettings(normal_lot_usd=75.0)
    out = sr.overlay_settings(s, {"normal_lot_usd": 120.0, "rsi_reset_max": 40.0})
    assert out.normal_lot_usd == 120.0
    assert out.rsi_reset_max == 40.0
    assert s.normal_lot_usd == 75.0  # original untouched (copy)


def test_overlay_never_touches_account_level():
    s = RiskSettings(max_concurrent_positions=8, max_spread_pct=0.5, normal_lot_usd=75.0)
    out = sr.overlay_settings(s, {"max_concurrent_positions": 1, "max_spread_pct": 5.0,
                                  "normal_lot_usd": 200.0})
    assert out.max_concurrent_positions == 8   # account-level preserved
    assert out.max_spread_pct == 0.5           # account-level preserved
    assert out.normal_lot_usd == 200.0         # strategy-level applied


@pytest.mark.asyncio
async def test_resolve_active_params_reads_active_config():
    cfg = {"id": "c1", "tenant_id": "owner", "strategy_key": "hunter",
           "strategy_version": "1.0.0",
           "params": {"rsi_reset_max": 42.0, "normal_lot_usd": 150.0,
                      "max_concurrent_positions": 2}}  # account-level → must be dropped
    db = _DB(metas=[{"key": "hunter", "active_config_id": "c1"},
                    {"key": "squeeze", "active_config_id": None}],
             configs=[cfg])
    out = await sr.resolve_active_params(db)
    assert "hunter" in out and "squeeze" not in out
    assert out["hunter"]["rsi_reset_max"] == 42.0
    assert out["hunter"]["normal_lot_usd"] == 150.0
    assert "max_concurrent_positions" not in out["hunter"]  # account-level stripped


@pytest.mark.asyncio
async def test_resolve_clamps_out_of_range():
    cfg = {"id": "c2", "tenant_id": "owner", "strategy_key": "squeeze",
           "strategy_version": "1.0.0",
           "params": {"squeeze_vol_expansion_min": 99.0}}  # clamp hi = 5.0
    db = _DB(metas=[{"key": "squeeze", "active_config_id": "c2"}], configs=[cfg])
    out = await sr.resolve_active_params(db)
    assert out["squeeze"]["squeeze_vol_expansion_min"] == 5.0


@pytest.mark.asyncio
async def test_resolve_empty_when_no_active():
    db = _DB(metas=[{"key": "hunter", "active_config_id": None}], configs=[])
    assert await sr.resolve_active_params(db) == {}
