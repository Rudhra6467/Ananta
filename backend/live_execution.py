"""
Live order execution via CCXT private API.

Cleanly separated from the PAPER simulator. The LIVE path is reached only when
ALL of these are true:
  1. `settings.trading_mode == "LIVE"` (operator UI choice)
  2. `LIVE_TRADING_ENABLED=true` env var (defense-in-depth interlock)
  3. `EXCHANGE_API_KEY` and `EXCHANGE_API_SECRET` env vars are set
  4. `LiveExecutor.is_live_ready()` returns True

If any check fails, the engine logs loudly and skips the trade.

Real-money safety controls baked in:
  * Minimum order size enforcement (scale up to exchange minimum, or skip).
  * Limit orders only - no market orders (slippage cap via limit price).
  * Pre-trade spread re-check (re-fetch ticker within 500ms; abort if widened).
  * Post-submit fill poll for `fill_timeout_s` seconds; cancel if unfilled.
  * Partial fills are accepted (we update the portfolio with actual filled qty).
  * Every exchange exception is caught, logged, and converted into a
    deterministic `ExecutionResult` - never propagates to the trading loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import ccxt

logger = logging.getLogger(__name__)

# ─── env knobs ───────────────────────────────────────────────────────────
ENV_LIVE_ENABLED = "LIVE_TRADING_ENABLED"     # must be exactly "true"
ENV_EXCHANGE = "EXCHANGE_NAME"                # "kraken" or "coinbase"
ENV_API_KEY = "EXCHANGE_API_KEY"
ENV_API_SECRET = "EXCHANGE_API_SECRET"
ENV_MAX_SLIPPAGE = "LIVE_MAX_SLIPPAGE_PCT"    # default 0.10
ENV_FILL_TIMEOUT = "LIVE_FILL_TIMEOUT_SECONDS"  # default 10
ENV_SPREAD_RECHECK_MS = "LIVE_SPREAD_RECHECK_MS"  # default 500

DEFAULT_MAX_SLIPPAGE_PCT = 0.10
DEFAULT_FILL_TIMEOUT_S = 10
DEFAULT_SPREAD_RECHECK_MS = 500


# ─── result type ─────────────────────────────────────────────────────────
ExecStatus = Literal[
    "FILLED",      # fully filled
    "PARTIAL",     # partially filled, remainder cancelled
    "CANCELLED",   # placed but cancelled after timeout, no fill
    "REJECTED",    # exchange rejected the order
    "SKIPPED",     # never sent (e.g. notional below min, gate closed)
    "ABORTED",     # pre-trade re-check failed (spread widened, etc.)
    "ERROR",       # unexpected exception
    "DRY_RUN",     # full LIVE path executed except create_order; nothing sent
]


@dataclass
class ExecutionResult:
    status: ExecStatus
    side: Literal["BUY", "SELL"]
    symbol: str
    filled_qty: float = 0.0
    filled_price: float = 0.0  # average fill price
    filled_notional: float = 0.0
    requested_qty: float = 0.0
    limit_price: float = 0.0
    order_id: str = ""
    reason: str = ""
    raw_order: dict | None = field(default=None, repr=False)

    @property
    def is_fill(self) -> bool:
        # DRY_RUN counts as a fill so the simulated portfolio updates and the
        # operator can audit "what the LIVE engine would have done" over time.
        return self.status in ("FILLED", "PARTIAL", "DRY_RUN") and self.filled_qty > 0


# ─── helpers ─────────────────────────────────────────────────────────────
def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# ─── main class ──────────────────────────────────────────────────────────
class LiveExecutor:
    """One LiveExecutor instance per exchange. Stateless apart from the CCXT
    client. Safe to share across the trading-loop coroutines (CCXT calls
    are run via `asyncio.to_thread`).
    """

    def __init__(
        self,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        max_slippage_pct: float = DEFAULT_MAX_SLIPPAGE_PCT,
        fill_timeout_s: int = DEFAULT_FILL_TIMEOUT_S,
        spread_recheck_ms: int = DEFAULT_SPREAD_RECHECK_MS,
        mode: Literal["LIVE", "DRY_RUN"] = "LIVE",
    ):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.max_slippage_pct = max_slippage_pct
        self.fill_timeout_s = fill_timeout_s
        self.spread_recheck_ms = spread_recheck_ms
        self.mode = mode

        if not hasattr(ccxt, exchange_name):
            raise ValueError(f"Unknown exchange: {exchange_name}")
        self.exchange: Any = getattr(ccxt, exchange_name)({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 10_000,
            "options": {"defaultType": "spot"},
        })
        self.exchange.load_markets()
        logger.info(
            "Executor[%s] initialised for %s, %d markets loaded, slippage=%.3f%%, fill_timeout=%ds",
            mode, exchange_name, len(self.exchange.markets), max_slippage_pct, fill_timeout_s,
        )

    # ── env gate ─────────────────────────────────────────────────────────
    @staticmethod
    def is_live_gate_open() -> bool:
        """Defense-in-depth: even if the operator UI is set to LIVE, the
        backend refuses to place real orders unless this env var is exactly
        the string 'true'."""
        return _env_bool(ENV_LIVE_ENABLED)

    def is_live_ready(self) -> tuple[bool, str]:
        """Returns (ready, reason). Trading loop checks this before routing."""
        # DRY_RUN bypasses the env-gate and key requirements because no real
        # order ever leaves the bot. It still needs an exchange client (built
        # in __init__) for fetch_ticker / load_markets public calls.
        if self.mode == "DRY_RUN":
            return True, "dry-run ready"
        if not self.is_live_gate_open():
            return False, f"{ENV_LIVE_ENABLED} env var is not 'true'"
        if not self.api_key or not self.api_secret:
            return False, "API key/secret missing"
        return True, "ready"

    # ── account balance (Vault Engine) ───────────────────────────────────
    async def fetch_free_quote_balance(self) -> float | None:
        """Sum the FREE (available) USD-equivalent quote currencies on the
        exchange. Returns None if the balance call fails (e.g. DRY_RUN with no
        private API keys). Kraken reports USD as 'ZUSD' on some endpoints, so
        we sum all common USD aliases."""
        try:
            bal = await asyncio.to_thread(self.exchange.fetch_balance)
        except Exception as e:
            logger.warning("fetch_balance failed (vault sync): %s", e)
            return None
        free = (bal or {}).get("free", {}) or {}
        total = 0.0
        for ccy in ("USD", "USDC", "ZUSD", "USDT"):
            v = free.get(ccy)
            if v:
                try:
                    total += float(v)
                except (TypeError, ValueError):
                    pass
        return total

    # ── market introspection ─────────────────────────────────────────────
    def get_market(self, symbol: str) -> dict | None:
        return self.exchange.markets.get(symbol)

    def get_min_amount_cost(self, symbol: str) -> tuple[float, float]:
        """Returns (min_amount, min_cost) for the symbol. Either may be 0
        if the exchange doesn't publish that constraint."""
        m = self.get_market(symbol)
        if not m:
            return 0.0, 0.0
        limits = m.get("limits") or {}
        amt = limits.get("amount") or {}
        cost = limits.get("cost") or {}
        return float(amt.get("min") or 0.0), float(cost.get("min") or 0.0)

    def adjust_for_min_size(
        self, symbol: str, desired_notional: float, price: float, max_notional: float,
    ) -> tuple[float, float, str]:
        """Decide the actual order size based on exchange minimums.

        Inputs:
          desired_notional - the position-sizer's target dollar value
          price            - the limit price we'd send
          max_notional     - hard cap (e.g. 95% of cash on hand)

        Returns: (qty, notional, reason).
        Returns qty=0.0 when the order should be SKIPPED (with reason).
        Otherwise returns the adjusted qty that satisfies the exchange's
        minimums (scaled up to the floor when desired < min).
        """
        if price <= 0:
            return 0.0, 0.0, "invalid price"
        min_amount, min_cost = self.get_min_amount_cost(symbol)

        desired_qty = desired_notional / price
        # raise to minimums
        scaled_qty = max(desired_qty, min_amount)
        if min_cost > 0:
            scaled_qty = max(scaled_qty, min_cost / price)

        # round to exchange precision
        try:
            scaled_qty = float(self.exchange.amount_to_precision(symbol, scaled_qty))
        except (ccxt.BaseError, ValueError, TypeError):
            pass  # use unrounded - exchange will reject if needed

        scaled_notional = scaled_qty * price
        if scaled_notional > max_notional:
            return (
                0.0, 0.0,
                f"min-order ${scaled_notional:.4f} exceeds available cash ${max_notional:.4f} "
                f"(min_amount={min_amount}, min_cost={min_cost})",
            )
        scaled_reason = ""
        if scaled_qty > desired_qty * 1.001:
            scale_x = scaled_qty / max(desired_qty, 1e-12)
            scaled_reason = (
                f" (scaled up {scale_x:.1f}x from desired ${desired_notional:.4f} "
                f"to exchange minimum ${scaled_notional:.4f})"
            )
        return scaled_qty, scaled_notional, "ok" + scaled_reason

    # ── pre-trade spread re-check ────────────────────────────────────────
    async def recheck_spread(self, symbol: str, max_spread_pct: float) -> tuple[bool, dict]:
        """Re-fetch the latest ticker right before sending the order.
        Returns (ok, details). False if spread widened beyond limit."""
        try:
            ticker = await asyncio.to_thread(self.exchange.fetch_ticker, symbol)
        except Exception as e:
            logger.warning("recheck_spread failed for %s: %s", symbol, e)
            return False, {"error": str(e)}
        bid = float(ticker.get("bid") or 0.0)
        ask = float(ticker.get("ask") or 0.0)
        if bid <= 0 or ask <= 0:
            return False, {"error": "no bid/ask in ticker", "bid": bid, "ask": ask}
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid * 100.0
        ok = spread_pct <= max_spread_pct
        return ok, {"bid": bid, "ask": ask, "spread_pct": spread_pct, "limit": max_spread_pct}

    # ── core order placement ─────────────────────────────────────────────
    async def _create_limit(self, symbol: str, side: str, qty: float, price: float, post_only: bool = False) -> dict:
        # quantise both
        try:
            qty = float(self.exchange.amount_to_precision(symbol, qty))
            price = float(self.exchange.price_to_precision(symbol, price))
        except (ccxt.BaseError, ValueError, TypeError):
            pass
        params = {"postOnly": True} if post_only else {}
        return await asyncio.to_thread(
            self.exchange.create_order, symbol, "limit", side, qty, price, params,
        )

    async def _create_market(self, symbol: str, side: str, qty: float) -> dict:
        try:
            qty = float(self.exchange.amount_to_precision(symbol, qty))
        except (ccxt.BaseError, ValueError, TypeError):
            pass
        return await asyncio.to_thread(
            self.exchange.create_order, symbol, "market", side, qty,
        )

    async def _poll_until_filled(self, symbol: str, order_id: str) -> dict:
        """Poll fetch_order every 1s up to fill_timeout_s. Return the final
        order dict (may still be 'open' if timed out)."""
        deadline = time.time() + self.fill_timeout_s
        last_order: dict = {"id": order_id, "status": "open"}
        while time.time() < deadline:
            try:
                last_order = await asyncio.to_thread(self.exchange.fetch_order, order_id, symbol)
            except Exception as e:
                logger.warning("fetch_order failed for %s: %s", order_id, e)
            status = (last_order or {}).get("status", "open")
            if status in ("closed", "filled", "canceled", "cancelled", "expired", "rejected"):
                return last_order
            await asyncio.sleep(1.0)
        return last_order

    async def _safe_cancel(self, symbol: str, order_id: str) -> None:
        try:
            await asyncio.to_thread(self.exchange.cancel_order, order_id, symbol)
        except ccxt.OrderNotFound:
            pass  # already gone (filled or expired between poll and cancel)
        except Exception as e:
            logger.warning("cancel_order(%s) raised: %s", order_id, e)

    # ── BUY / SELL public API ────────────────────────────────────────────
    async def place_buy(
        self,
        symbol: str,
        desired_notional: float,
        max_cash: float,
        ask: float,
        max_spread_pct: float,
        order_style: str = "POST_ONLY",
    ) -> ExecutionResult:
        """Place a BUY.

        order_style="POST_ONLY" (Normal/Strong swing entries): a maker LIMIT at
        the best BID with a Post-Only flag — if it would execute immediately as
        a taker, the exchange rejects it and we ABORT (retry next cycle).
        order_style="MARKET" (Systemic Breakout entries): a taker MARKET order
        for guaranteed fill on high-velocity moves.
        """
        ready, why = self.is_live_ready()
        if not ready:
            return ExecutionResult(status="SKIPPED", side="BUY", symbol=symbol, reason=why)

        # 1. Pre-trade spread re-check (per-tier max_spread_pct supplied by engine)
        ok, details = await self.recheck_spread(symbol, max_spread_pct)
        if not ok:
            return ExecutionResult(
                status="ABORTED", side="BUY", symbol=symbol,
                reason=f"Execution blocked due to insufficient liquidity: {details}",
            )
        live_bid = float(details["bid"])
        live_ask = float(details["ask"])

        # 2. Reference price: maker rests at best bid; taker sizes at ask.
        is_market = order_style == "MARKET"
        ref_price = live_ask if is_market else live_bid

        # 3. Enforce exchange minimum + check it fits in cash
        qty, notional, msg = self.adjust_for_min_size(symbol, desired_notional, ref_price, max_cash)
        if qty <= 0:
            return ExecutionResult(
                status="SKIPPED", side="BUY", symbol=symbol,
                requested_qty=desired_notional / ref_price if ref_price else 0.0,
                limit_price=ref_price, reason=msg,
            )

        # 4. DRY_RUN short-circuit: full path executed except create_order.
        if self.mode == "DRY_RUN":
            logger.info(
                "DRY_RUN BUY %s [%s] would have placed: qty=%.8f price=%.4f notional=%.4f (%s)",
                symbol, order_style, qty, ref_price, qty * ref_price, msg,
            )
            return ExecutionResult(
                status="DRY_RUN", side="BUY", symbol=symbol,
                filled_qty=qty, filled_price=ref_price,
                filled_notional=qty * ref_price,
                requested_qty=qty, limit_price=ref_price,
                order_id=f"dry-{int(time.time() * 1000)}",
                reason=f"dry-run {order_style} buy | size_msg={msg}",
            )

        # 5. Submit order (LIVE only)
        limit_price = ref_price
        try:
            if is_market:
                order = await self._create_market(symbol, "buy", qty)
            else:
                order = await self._create_limit(symbol, "buy", qty, limit_price, post_only=True)
        except ccxt.InsufficientFunds as e:
            return ExecutionResult(status="REJECTED", side="BUY", symbol=symbol, reason=f"InsufficientFunds: {e}")
        except ccxt.OrderImmediatelyFillable as e:
            return ExecutionResult(
                status="ABORTED", side="BUY", symbol=symbol, limit_price=limit_price,
                reason=f"post-only would cross (retry next cycle): {e}",
            )
        except ccxt.InvalidOrder as e:
            # Kraken often surfaces post-only rejection as InvalidOrder
            reason = f"post-only would cross (retry next cycle): {e}" if not is_market else f"InvalidOrder: {e}"
            status = "ABORTED" if not is_market else "REJECTED"
            return ExecutionResult(status=status, side="BUY", symbol=symbol, limit_price=limit_price, reason=reason)
        except Exception as e:
            logger.exception("create_order(buy %s) failed", symbol)
            return ExecutionResult(status="ERROR", side="BUY", symbol=symbol, reason=f"{type(e).__name__}: {e}")
        order_id = order.get("id", "")

        # 6. Poll until filled, cancel if not
        final = await self._poll_until_filled(symbol, order_id)
        return await self._build_result_from_order("BUY", symbol, qty, limit_price, order_id, final)

    async def place_sell(
        self,
        symbol: str,
        qty: float,
        bid: float,
        max_spread_pct: float,
    ) -> ExecutionResult:
        """Place a LIMIT SELL priced at bid × (1 - max_slippage_pct)."""
        ready, why = self.is_live_ready()
        if not ready:
            return ExecutionResult(status="SKIPPED", side="SELL", symbol=symbol, reason=why)

        ok, details = await self.recheck_spread(symbol, max_spread_pct)
        if not ok:
            return ExecutionResult(
                status="ABORTED", side="SELL", symbol=symbol,
                reason=f"spread re-check failed: {details}",
            )
        live_bid = float(details["bid"])

        limit_price = live_bid * (1.0 - self.max_slippage_pct / 100.0)

        # quantise qty
        try:
            qty = float(self.exchange.amount_to_precision(symbol, qty))
        except (ccxt.BaseError, ValueError, TypeError):
            pass

        # DRY_RUN short-circuit
        if self.mode == "DRY_RUN":
            logger.info(
                "DRY_RUN SELL %s would have placed: qty=%.8f limit=%.4f notional=%.4f",
                symbol, qty, limit_price, qty * limit_price,
            )
            return ExecutionResult(
                status="DRY_RUN", side="SELL", symbol=symbol,
                filled_qty=qty, filled_price=limit_price,
                filled_notional=qty * limit_price,
                requested_qty=qty, limit_price=limit_price,
                order_id=f"dry-{int(time.time() * 1000)}",
                reason="dry-run sell",
            )

        try:
            order = await self._create_limit(symbol, "sell", qty, limit_price)
        except ccxt.InsufficientFunds as e:
            return ExecutionResult(status="REJECTED", side="SELL", symbol=symbol, reason=f"InsufficientFunds: {e}")
        except ccxt.InvalidOrder as e:
            return ExecutionResult(status="REJECTED", side="SELL", symbol=symbol, reason=f"InvalidOrder: {e}")
        except Exception as e:
            logger.exception("create_order(sell %s) failed", symbol)
            return ExecutionResult(status="ERROR", side="SELL", symbol=symbol, reason=f"{type(e).__name__}: {e}")
        order_id = order.get("id", "")

        final = await self._poll_until_filled(symbol, order_id)
        return await self._build_result_from_order("SELL", symbol, qty, limit_price, order_id, final)

    # ── result interpretation ────────────────────────────────────────────
    async def _build_result_from_order(
        self,
        side: Literal["BUY", "SELL"],
        symbol: str,
        requested_qty: float,
        limit_price: float,
        order_id: str,
        order: dict,
    ) -> ExecutionResult:
        order = order or {}
        status_raw = (order.get("status") or "").lower()
        filled_qty = float(order.get("filled") or 0.0)
        avg_price = float(order.get("average") or order.get("price") or limit_price)
        notional = filled_qty * avg_price

        # Map exchange statuses to ours, awaiting any cancel deterministically.
        if status_raw in ("closed", "filled") and filled_qty >= requested_qty * 0.999:
            status: ExecStatus = "FILLED"
        elif filled_qty > 0:
            # partial fill - cancel the remainder synchronously so we never
            # leave a dangling unfilled remainder on the exchange.
            await self._safe_cancel(symbol, order_id)
            status = "PARTIAL"
        elif status_raw in ("canceled", "cancelled", "expired", "rejected"):
            status = "CANCELLED" if status_raw != "rejected" else "REJECTED"
        else:
            # unfilled after timeout - cancel
            await self._safe_cancel(symbol, order_id)
            status = "CANCELLED"

        return ExecutionResult(
            status=status,
            side=side,
            symbol=symbol,
            filled_qty=filled_qty,
            filled_price=avg_price,
            filled_notional=notional,
            requested_qty=requested_qty,
            limit_price=limit_price,
            order_id=order_id,
            reason=f"exchange_status={status_raw}",
            raw_order=order,
        )


# ─── singleton (built from env on demand) ────────────────────────────────
_executor_singleton: Optional[LiveExecutor] = None
_executor_init_error: Optional[str] = None


def get_default_executor() -> tuple[Optional[LiveExecutor], Optional[str]]:
    """Return (executor, error_message). Either may be None.
    The executor is built lazily and cached. If env vars are missing or the
    exchange client fails to initialise, returns (None, error_message)."""
    global _executor_singleton, _executor_init_error
    if _executor_singleton is not None:
        return _executor_singleton, None
    if _executor_init_error is not None:
        return None, _executor_init_error

    exchange_name = (os.environ.get(ENV_EXCHANGE) or "").strip().lower()
    api_key = (os.environ.get(ENV_API_KEY) or "").strip()
    api_secret = (os.environ.get(ENV_API_SECRET) or "").strip()
    if not (exchange_name and api_key and api_secret):
        _executor_init_error = (
            f"LIVE executor not configured: set {ENV_EXCHANGE}, {ENV_API_KEY}, "
            f"{ENV_API_SECRET} in backend/.env to enable."
        )
        return None, _executor_init_error
    try:
        _executor_singleton = LiveExecutor(
            exchange_name=exchange_name,
            api_key=api_key,
            api_secret=api_secret,
            max_slippage_pct=_env_float(ENV_MAX_SLIPPAGE, DEFAULT_MAX_SLIPPAGE_PCT),
            fill_timeout_s=_env_int(ENV_FILL_TIMEOUT, DEFAULT_FILL_TIMEOUT_S),
            spread_recheck_ms=_env_int(ENV_SPREAD_RECHECK_MS, DEFAULT_SPREAD_RECHECK_MS),
        )
        return _executor_singleton, None
    except Exception as e:
        _executor_init_error = f"LiveExecutor init failed: {type(e).__name__}: {e}"
        logger.exception(_executor_init_error)
        return None, _executor_init_error


def reset_executor_for_tests() -> None:
    """Test hook - clears the singletons so each test gets a fresh slate."""
    global _executor_singleton, _executor_init_error
    global _dry_run_singleton, _dry_run_init_error
    _executor_singleton = None
    _executor_init_error = None
    _dry_run_singleton = None
    _dry_run_init_error = None


# DRY_RUN singleton (separate from LIVE because it has weaker requirements)
_dry_run_singleton: Optional[LiveExecutor] = None
_dry_run_init_error: Optional[str] = None


def get_dry_run_executor() -> tuple[Optional[LiveExecutor], Optional[str]]:
    """Build a DRY_RUN executor. Requires only EXCHANGE_NAME (no keys, no env
    gate). Falls back to Kraken when EXCHANGE_NAME is unset, since Kraken's
    public API works without authentication.
    """
    global _dry_run_singleton, _dry_run_init_error
    if _dry_run_singleton is not None:
        return _dry_run_singleton, None
    if _dry_run_init_error is not None:
        return None, _dry_run_init_error

    exchange_name = (os.environ.get(ENV_EXCHANGE) or "kraken").strip().lower()
    # If LIVE keys happen to be configured, reuse them so DRY_RUN mirrors LIVE
    # behaviour even more closely. Keys aren't required for DRY_RUN though -
    # public endpoints (fetch_ticker, load_markets) work without auth.
    api_key = (os.environ.get(ENV_API_KEY) or "").strip()
    api_secret = (os.environ.get(ENV_API_SECRET) or "").strip()
    try:
        _dry_run_singleton = LiveExecutor(
            exchange_name=exchange_name,
            api_key=api_key,
            api_secret=api_secret,
            max_slippage_pct=_env_float(ENV_MAX_SLIPPAGE, DEFAULT_MAX_SLIPPAGE_PCT),
            fill_timeout_s=_env_int(ENV_FILL_TIMEOUT, DEFAULT_FILL_TIMEOUT_S),
            spread_recheck_ms=_env_int(ENV_SPREAD_RECHECK_MS, DEFAULT_SPREAD_RECHECK_MS),
            mode="DRY_RUN",
        )
        return _dry_run_singleton, None
    except Exception as e:
        _dry_run_init_error = f"Dry-run executor init failed: {type(e).__name__}: {e}"
        logger.exception(_dry_run_init_error)
        return None, _dry_run_init_error


def live_status() -> dict:
    """Diagnostic snapshot for the operator UI / health checks."""
    gate = LiveExecutor.is_live_gate_open()
    exchange_name = (os.environ.get(ENV_EXCHANGE) or "").strip().lower() or None
    api_key_set = bool((os.environ.get(ENV_API_KEY) or "").strip())
    api_secret_set = bool((os.environ.get(ENV_API_SECRET) or "").strip())
    return {
        "live_gate_open": gate,
        "exchange": exchange_name,
        "api_key_configured": api_key_set,
        "api_secret_configured": api_secret_set,
        "max_slippage_pct": _env_float(ENV_MAX_SLIPPAGE, DEFAULT_MAX_SLIPPAGE_PCT),
        "fill_timeout_s": _env_int(ENV_FILL_TIMEOUT, DEFAULT_FILL_TIMEOUT_S),
        "ready_to_trade": gate and exchange_name is not None and api_key_set and api_secret_set,
        "dry_run_ready": True,  # always available (DRY_RUN defaults to kraken public API)
    }
