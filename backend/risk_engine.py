"""
Layer 5 & 6 - AI Fusion + Risk Controls.
Evaluates kill-switches and produces a final decision (BUY / SELL / HOLD / BLOCKED).
"""
from __future__ import annotations

from typing import List, Tuple

from models import KillSwitchStatus, MarketSnapshot, Portfolio, RiskSettings


def compute_kill_switches(
    snapshot: MarketSnapshot,
    portfolio: Portfolio,
    settings: RiskSettings,
    macro_confidence: float,
) -> KillSwitchStatus:
    """Evaluate all hard kill-switches.
    Returns a KillSwitchStatus with overall_safe=False if ANY breach.
    """
    # current equity = cash + sum(positions * last_price). For simplicity we approximate
    # equity using cash + cost_basis (we recompute properly at the engine layer for daily P&L).
    current_equity = portfolio.cash + sum(p.cost_basis for p in portfolio.positions)
    day_start = portfolio.day_start_equity or portfolio.starting_balance
    daily_change_pct = ((current_equity - day_start) / day_start * 100.0) if day_start > 0 else 0.0

    spread_breach = snapshot.spread_pct > settings.max_spread_pct
    daily_loss_breach = daily_change_pct <= -settings.max_daily_loss_pct
    confidence_breach = macro_confidence < settings.min_confidence
    manual_kill = bool(settings.manual_kill_switch)

    overall_safe = not (spread_breach or daily_loss_breach or manual_kill)
    # confidence_breach blocks new trades but isn't a "TERMINATED" hard stop on its own

    return KillSwitchStatus(
        spread_breach=spread_breach,
        daily_loss_breach=daily_loss_breach,
        confidence_breach=confidence_breach,
        manual_kill=manual_kill,
        overall_safe=overall_safe,
        details={
            "spread_pct": round(snapshot.spread_pct, 4),
            "max_spread_pct": settings.max_spread_pct,
            "daily_change_pct": round(daily_change_pct, 4),
            "max_daily_loss_pct": settings.max_daily_loss_pct,
            "macro_confidence": round(macro_confidence, 3),
            "min_confidence": settings.min_confidence,
            "current_equity": round(current_equity, 4),
            "day_start_equity": round(day_start, 4),
        },
    )


def fuse_signals(
    snapshot: MarketSnapshot,
    macro_bias: str,
    macro_confidence: float,
    settings: RiskSettings,
    kill: KillSwitchStatus,
    has_position: bool,
    htf_trend_aligned: bool | None = None,
    at_support: bool = False,
    support_zone: dict | None = None,
    primary_triggered: bool | None = None,
    breaker_state: str = "PASS",
) -> Tuple[str, List[str], str]:
    """TECHNICAL-FIRST fusion — Hunter + tri-state Circuit Breaker.

    Returns (decision, blocked_reasons, fusion_summary). Decision: BUY / SELL / HOLD / BLOCKED.

    Architecture:
      * The PRIMARY technical layer (Hunter) is the SOLE entry driver. Macro/news/
        sentiment NEVER create, rescue, or block an entry.
      * The SECONDARY layer is a tri-state Circuit Breaker (PASS / CAUTION / VETO).
        Only VETO acts here, and VETO is EXISTENTIAL-ONLY (hack/insolvency/reg
        shutdown). CAUTION proceeds normally (logged elsewhere). Sentiment/macro
        bearishness can never reach VETO.
      * Open positions are managed entirely by the exit engine (structural stop +
        trailing take-profit); the breaker force-exits only on an existential VETO.
    """
    blocked: List[str] = []
    if kill.manual_kill:
        blocked.append("MANUAL_KILL")
    if kill.spread_breach:
        blocked.append(f"SPREAD_BREACH spread={kill.details['spread_pct']}% > {settings.max_spread_pct}%")
    if kill.daily_loss_breach:
        blocked.append(f"DAILY_LOSS_BREACH equity={kill.details['daily_change_pct']}% <= -{settings.max_daily_loss_pct}%")

    if kill.manual_kill or kill.spread_breach or kill.daily_loss_breach:
        summary = (
            f"BLOCKED by risk engine. Hard kill-switch triggered. "
            f"macro bias {macro_bias} @ {macro_confidence:.2f}."
        )
        return "BLOCKED", blocked, summary

    breaker_veto = breaker_state == "VETO"

    # --- open position: exits owned by the watcher; breaker force-exits ONLY on an
    # existential VETO (never on sentiment/macro). ---
    if has_position:
        if breaker_veto:
            return "SELL", blocked, "SELL - EXISTENTIAL circuit-breaker VETO. Emergency exit to preserve capital."
        return "HOLD", blocked, "HOLD - position open; risk managed by structural stop + trailing exit."

    # --- flat: the Hunter is the sole entry driver; breaker can only VETO (existential). ---
    if breaker_veto:
        blocked.append("REJECTED_SECONDARY_VETO_EXISTENTIAL")
        return "HOLD", blocked, "HOLD - existential circuit-breaker VETO active; standing aside."

    # LAYERED MODE (live engine): the PRIMARY Hunter decides.
    if primary_triggered is not None:
        if primary_triggered and getattr(settings, "level_entry_enabled", True):
            z = support_zone or {}
            summary = (
                f"BUY (HUNTER): {snapshot.price:.4f} cleared all technical gates at support "
                f"[{z.get('low')}–{z.get('high')}], touches={z.get('touches')}. Structural stop armed."
            )
            return "BUY", blocked, summary
        summary = "HOLD - Hunter technical layer not satisfied (see reason_codes)."
        return "HOLD", blocked, summary

    # --- LEGACY MODE (backtest/research only): support-touch or bullish-macro entry. ---
    if getattr(settings, "level_entry_enabled", True) and at_support:
        z = support_zone or {}
        summary = (
            f"BUY (LEVEL): price {snapshot.price:.4f} testing historical support "
            f"[{z.get('low')}–{z.get('high')}], touches={z.get('touches')}."
        )
        return "BUY", blocked, summary

    htf_required = settings.htf_trend_enabled and htf_trend_aligned is not None
    htf_ok = (not htf_required) or bool(htf_trend_aligned)
    if macro_bias == "BULLISH" and htf_ok:
        summary = (
            f"BUY (SWING legacy): macro {macro_bias} @ {macro_confidence:.2f}"
            + (" AND 4h trend aligned" if htf_required else "") + "."
        )
        return "BUY", blocked, summary

    if macro_bias == "BULLISH" and htf_required and not htf_ok:
        return "HOLD", blocked, (
            f"HOLD - macro {macro_bias} @ {macro_confidence:.2f} but 4h trend not aligned and no support touch."
        )

    return "HOLD", blocked, f"HOLD - no Hunter setup (macro {macro_bias} @ {macro_confidence:.2f})."


def position_size_quantity(
    decision: str,
    snapshot: MarketSnapshot,
    portfolio: Portfolio,
    settings: RiskSettings,
    macro_confidence: float,
    *,
    usd_lot: float | None = None,
) -> float:
    """Compute trade quantity for a BUY decision.

    Two paths:
      * adaptive (preferred): caller passes a fixed `usd_lot` (e.g. $5 normal,
        $10 strong). We size exactly that USD notional, capped at 95% of cash.
      * legacy: scale 1-3% of equity by confidence.
    """
    if decision != "BUY":
        return 0.0
    if usd_lot is not None and usd_lot > 0:
        notional = min(float(usd_lot), portfolio.cash * 0.95)
    else:
        equity = portfolio.cash + sum(p.cost_basis for p in portfolio.positions)
        # scale between min and max based on confidence
        spread = settings.position_size_pct_max - settings.position_size_pct_min
        pct = settings.position_size_pct_min + spread * max(0.0, min(1.0, macro_confidence))
        notional = equity * (pct / 100.0)
        notional = min(notional, portfolio.cash * 0.95)  # never use all cash
    if snapshot.ask <= 0 or notional <= 0:
        return 0.0
    qty = notional / snapshot.ask
    return round(qty, 8)
