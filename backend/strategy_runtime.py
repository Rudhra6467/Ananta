"""
strategy_runtime.py — P3 per-strategy engine config resolution.

WHY
---
Historically the live engine read EVERY tuning knob from the single global
`RiskSettings` document, so "activating" one strategy's config clobbered fields
shared by all strategies. P3 fixes this: each strategy resolves its OWN entry /
exit / lot params from its ACTIVE `strategy_config`, overlaid on top of the global
account-level baseline — WITHOUT touching account-level risk (which stays global).

CONTRACT
--------
- `resolve_active_params(db)` → {strategy_key: {engine_field: clamped_value}} for
  every strategy that has an active config on `strategy_meta`. Empty when none.
- `overlay_settings(base, params)` → a per-strategy COPY of RiskSettings with the
  strategy-level params applied. Account-level fields are NEVER overridden.
- Fully backward-compatible: with no active config the copy == the global settings,
  so engine behaviour is unchanged until an owner activates a config.

The same resolver powers a research→live promotion: a config validated in the
Research Lab can be activated for one strategy and it starts driving that
strategy's live/paper entries immediately, in isolation from the others.
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from settings_spec import clamp_value
from strategy.core import engine_backed_params, get_schema, resolve_config

logger = logging.getLogger("ananta.strategy_runtime")

_OWNER_TENANT = "owner"

# Account-level fields govern the WHOLE book, not one strategy. A per-strategy config
# may never override these — they stay owned by the global RiskSettings (the config split
# agreed in P3: strategy-level params per config, account-level risk stays global).
ACCOUNT_LEVEL_FIELDS: frozenset[str] = frozenset({
    "max_concurrent_positions",   # global slot cap
    "max_daily_loss_pct",         # account ruin-line
    "max_spread_pct",             # shared liquidity guard
    "taker_fee_pct", "maker_fee_pct", "breakout_paper_slippage_pct",  # exchange friction
    "vault_max_override_usd",     # deployable-capital ceiling
    "min_confidence",             # account-wide macro gate
})


async def resolve_active_params(db: AsyncIOMotorDatabase,
                                tenant_id: str = _OWNER_TENANT) -> dict[str, dict]:
    """Resolve the engine-backed, clamped, strategy-level params for every strategy
    that has an active config. Returns {} for strategies without one (→ global defaults)."""
    try:
        metas = await db.strategy_meta.find(
            {"active_config_id": {"$ne": None}},
            {"_id": 0, "key": 1, "active_config_id": 1}).to_list(200)
        if not metas:
            return {}
        rows = await db.strategy_configs.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(2000)
        by_id = {r["id"]: r for r in rows}
    except Exception as e:  # noqa: BLE001
        logger.warning("resolve_active_params failed: %s", e)
        return {}

    out: dict[str, dict] = {}
    for m in metas:
        cfg = by_id.get(m.get("active_config_id"))
        if not cfg:
            continue
        key = cfg["strategy_key"]
        schema = get_schema(key, cfg.get("strategy_version"))
        resolved = resolve_config(cfg, by_id, schema)
        engine = engine_backed_params(schema, resolved)
        params = {f: clamp_value(f, v) for f, v in engine.items()
                  if f not in ACCOUNT_LEVEL_FIELDS and v is not None}
        if params:
            out[key] = params
    return out


def overlay_settings(base_settings, params: dict | None):
    """Return a per-strategy COPY of `base_settings` with strategy-level `params` applied.
    Account-level fields are stripped defensively. No copy allocated when params is empty."""
    if not params:
        return base_settings
    clean = {k: v for k, v in params.items()
             if k not in ACCOUNT_LEVEL_FIELDS and hasattr(base_settings, k)}
    if not clean:
        return base_settings
    try:
        return base_settings.model_copy(update=clean)
    except Exception:  # noqa: BLE001 — never let config resolution break a trading cycle
        return base_settings
