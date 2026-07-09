# Ananta.AI — Configuration Architecture

_Last updated: 2026-07-09 (Settings unification, Option A)_

This document is the authoritative map of **where trading configuration lives, who
owns it, and how changes reach the live engine.** Read this before adding any new
tunable or config store.

## TL;DR

- **`RiskSettings` (the `settings` singleton) is the ONE source of truth the live
  engine reads.** Nothing else configures trading decisions.
- Three write-paths mutate it, all clamped through **`settings_spec.py`**.
- `strategy_configs` is a design/versioning layer that is **not** wired to the
  engine yet (Phase 2). It never silently affects live trading.

---

## Config stores

| Store (Mongo collection) | Model / shape | Owner / purpose | Read by the engine? |
|---|---|---|---|
| `settings` (`id="singleton"`) | `RiskSettings` (models.py) | **Live source of truth** — risk caps, entry/exit gates, sizing, fees, exchange creds, trading mode. Includes nested `profile_overrides`. | **YES** — via `trading_engine.load_settings()` |
| `settings.profile_overrides` (nested field) | `{strategy: {field: value}}` | Lab-promoted per-strategy **exit-profile** tweaks (e.g. `trail_atr_mult`). | YES — read by `exit_engine` |
| `strategy_meta` | `{key, status, enabled}` | Per-strategy **lifecycle status** (LIVE / PAPER / DISABLED). Gates whether a strategy may open new positions. Status only — not parameters. | YES — via `load_strategy_states()` (status gate only) |
| `strategy_configs` | `StrategyConfig` (strategy/core.py) | **Design & versioning layer** — Architect-authored, sparse overrides w/ inheritance, schema validation, rating. | **NO — Phase 2** |
| `lab_param_proposals` | proposal docs | Pending research promotions awaiting owner approval. | NO (applied → RiskSettings) |

---

## The single write-path to the engine (RiskSettings)

Exactly three code paths change `RiskSettings`. **All numeric values are clamped to
the hard bounds defined once in `settings_spec.py`** (`FLOAT_CLAMPS`, `INT_CLAMPS`,
`PROFILE_CLAMPS`).

1. **Direct owner edit** — `PUT /api/settings` → `server.update_settings`
   → `settings_spec.clamp_settings_dict(data)` → `save_settings`.
2. **Lab promotion** (manual approval gate) — owner reviews a run's proposed diff
   (`lab.proposals.build_diff`) then `POST /api/lab/proposals/{id}/apply`
   → `lab.proposals.apply_to_settings` (uses `settings_spec.clamp_value` /
   `clamp_profile_value`) → `save_settings`.
   - `set:<field>` → a `RiskSettings` field.
   - `prof:<strategy>:<field>` → `RiskSettings.profile_overrides[strategy][field]`.
3. **AI Coach apply** — `POST /api/coach/apply` → `coach.validate_apply`
   (narrow advisory whitelist `coach.APPLYABLE`, then defense-in-depth
   `settings_spec.clamp_value`) → `save_settings`.

> Advisory bands vs hard bounds: `coach.APPLYABLE` intentionally uses **narrower**
> bounds than `settings_spec` (safe, conservative nudges). `settings_spec` holds the
> **hard** sanity limits that no path may exceed.

Research/Lab values **never** auto-write — an owner always confirms (paths 2 & 3).

---

## Rules for future changes

- **New engine tunable?** Add the field to `RiskSettings`, add its hard bounds to
  `settings_spec` (`FLOAT_CLAMPS` / `INT_CLAMPS`), and read it via `load_settings`.
  Do **not** introduce a new collection the engine reads directly.
- **Never** add an engine read from `strategy_configs`, `strategy_meta` (beyond
  status), or `lab_param_proposals`.
- Keep clamp bounds in `settings_spec` only — do not re-declare per call-site.

---

## Phase 2 — per-strategy engine configs (compatible migration)

Goal: let each strategy carry its own resolved parameter set while keeping
`RiskSettings` as the engine's read interface (so no engine module changes).

Plan:
1. Mark one `strategy_configs` row per strategy as **active** (validated + owner-approved).
2. At cycle start, `resolve_config(active, by_id, schema)` (schema defaults ← parent
   chain ← self) → a flat param dict per strategy.
3. Merge each strategy's resolved params onto a **copy** of `RiskSettings` handed to
   that strategy's evaluation, still clamped via `settings_spec`.
4. Global/account-level risk (drawdown, daily loss, kill switch, concurrency) stays
   on the shared `RiskSettings`.

This keeps the current single-source contract intact and additive: until a config is
promoted active, behaviour is identical to today.
