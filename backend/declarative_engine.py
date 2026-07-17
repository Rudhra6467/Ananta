"""
declarative_engine.py — Phase B generic indicator/rule executor.

Runs a DECLARATIVE strategy spec (indicators + entry/exit conditions) against OHLCV
bars, so catalog strategies with no bespoke Python (EMA Cross, Supertrend, RSI Momentum,
MACD, Bollinger MR, Donchian, ATR/Keltner breakout…) can be wired to the live/paper
engine from data alone. Adding a new indicator strategy = add a spec, no engine changes.

Spec shape (see strategy/declarative_defs.py):
    {
      "indicators": {"ema_fast": {"fn": "ema", "period": "$ema_fast"}, ...},
      "entry": [{"lhs": "ema_fast", "op": "cross_above", "rhs": "ema_slow"}],   # AND-ed
      "exit":  [{"lhs": "ema_fast", "op": "cross_below", "rhs": "ema_slow"}],
    }

Operands: an indicator id | a price field ("close"/"open"/"high"/"low"/"prev_close")
| a number | "$param" (resolved from params). Bars are [ts, open, high, low, close, volume].
"""
from __future__ import annotations

from dataclasses import dataclass, field

_PRICE_IDX = {"open": 1, "high": 2, "low": 3, "close": 4, "volume": 5}


@dataclass
class DeclSignal:
    entry: bool = False
    exit: bool = False
    reason: str = ""
    indicators: dict = field(default_factory=dict)


# --------------------------- indicator primitives --------------------------- #
def _col(bars, key):
    i = _PRICE_IDX[key]
    return [float(b[i]) for b in bars]


def _ema(vals, period):
    if period <= 0 or len(vals) < 1:
        return [None] * len(vals)
    k = 2.0 / (period + 1)
    out, prev = [], None
    for i, v in enumerate(vals):
        if i + 1 < period:
            out.append(None); continue
        if prev is None:
            prev = sum(vals[i + 1 - period:i + 1]) / period
        else:
            prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def _sma(vals, period):
    out = []
    for i in range(len(vals)):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(vals[i + 1 - period:i + 1]) / period)
    return out


def _rsi(vals, period):
    out = [None] * len(vals)
    if len(vals) <= period:
        return out
    gains, losses = [], []
    for i in range(1, len(vals)):
        d = vals[i] - vals[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(vals)):
        if i > period:
            avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
            avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        rs = (avg_g / avg_l) if avg_l else 999.0
        out[i] = 100 - (100 / (1 + rs))
    return out


def _true_range(bars):
    tr = [None]
    for i in range(1, len(bars)):
        h, l, pc = float(bars[i][2]), float(bars[i][3]), float(bars[i - 1][4])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return tr


def _atr(bars, period):
    tr = _true_range(bars)
    out = [None] * len(bars)
    vals = [t for t in tr if t is not None]
    if len(vals) < period:
        return out
    prev = sum(tr[1:period + 1]) / period
    out[period] = prev
    for i in range(period + 1, len(bars)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def _shift(series, n):
    return [None] * n + series[:-n] if n > 0 else series


def _sma_series(series, period):
    """SMA over a series that may contain None; a window with any None yields None."""
    period = max(1, int(period))
    out = [None] * len(series)
    for i in range(len(series)):
        if i + 1 < period:
            continue
        window = series[i + 1 - period:i + 1]
        if any(x is None for x in window):
            continue
        out[i] = sum(window) / period
    return out


def _roc(vals, period):
    """Rate of change (%) over `period` bars: (v - v[-period]) / v[-period] * 100."""
    period = max(1, int(period))
    out = [None] * len(vals)
    for i in range(period, len(vals)):
        base = vals[i - period]
        out[i] = ((vals[i] - base) / base * 100.0) if base else 0.0
    return out


def _stoch(bars, k_period, smooth, d_period, want):
    """Stochastic oscillator. Returns smoothed %K or %D as a full-length series."""
    highs = _col(bars, "high"); lows = _col(bars, "low"); close = _col(bars, "close")
    k_period = max(1, int(k_period)); n = len(bars)
    raw = [None] * n
    for i in range(n):
        if i + 1 < k_period:
            continue
        ll = min(lows[i + 1 - k_period:i + 1]); hh = max(highs[i + 1 - k_period:i + 1])
        raw[i] = 100.0 * (close[i] - ll) / (hh - ll) if hh > ll else 50.0
    k = _sma_series(raw, smooth)
    if want == "stoch_k":
        return k
    return _sma_series(k, d_period)


def _vwap(bars, period):
    """Rolling volume-weighted average price over `period` bars (typical price)."""
    period = max(1, int(period)); n = len(bars)
    tp = [(float(b[2]) + float(b[3]) + float(b[4])) / 3 for b in bars]
    vol = _col(bars, "volume"); out = [None] * n
    for i in range(n):
        if i + 1 < period:
            continue
        pv = sum(tp[j] * vol[j] for j in range(i + 1 - period, i + 1))
        vv = sum(vol[j] for j in range(i + 1 - period, i + 1))
        out[i] = (pv / vv) if vv > 0 else tp[i]
    return out


def _vwap_band(bars, period, sigma, upper):
    """VWAP ± sigma × rolling std(close) band."""
    period = max(1, int(period)); vw = _vwap(bars, period); close = _col(bars, "close")
    n = len(bars); out = [None] * n
    for i in range(n):
        if vw[i] is None:
            continue
        window = close[i + 1 - period:i + 1]
        m = sum(window) / period
        sd = (sum((x - m) ** 2 for x in window) / period) ** 0.5
        out[i] = vw[i] + sigma * sd if upper else vw[i] - sigma * sd
    return out


def _build(name, spec, bars, params):
    fn = spec["fn"]
    p = lambda k, d=None: _resolve_num(spec.get(k, d), params)  # noqa: E731
    close = _col(bars, "close")
    if fn == "ema":
        return _ema(close, int(p("period")))
    if fn == "sma":
        return _sma(close, int(p("period")))
    if fn == "rsi":
        return _rsi(close, int(p("period")))
    if fn == "atr":
        return _atr(bars, int(p("period")))
    if fn in ("macd_line", "macd_signal", "macd_hist"):
        fast = _ema(close, int(p("fast", 12))); slow = _ema(close, int(p("slow", 26)))
        line = [(f - s) if (f is not None and s is not None) else None for f, s in zip(fast, slow)]
        if fn == "macd_line":
            return line
        sig = _ema([x if x is not None else 0.0 for x in line], int(p("signal", 9)))
        sig = [s if line[i] is not None else None for i, s in enumerate(sig)]
        if fn == "macd_signal":
            return sig
        return [(l - s) if (l is not None and s is not None) else None for l, s in zip(line, sig)]
    if fn in ("bb_lower", "bb_mid", "bb_upper"):
        period = int(p("period", 20)); std = p("std", 2.0)
        mid = _sma(close, period); out = []
        for i in range(len(close)):
            if mid[i] is None:
                out.append(None); continue
            window = close[i + 1 - period:i + 1]
            m = mid[i]; var = sum((x - m) ** 2 for x in window) / period; sd = var ** 0.5
            out.append(m if fn == "bb_mid" else (m - std * sd if fn == "bb_lower" else m + std * sd))
        return out
    if fn in ("donchian_high", "donchian_low"):
        period = int(p("period", 20)); highs = _col(bars, "high"); lows = _col(bars, "low"); out = []
        for i in range(len(bars)):
            if i < period:
                out.append(None); continue
            window = range(i - period, i)  # PRIOR N bars (exclude current → true breakout)
            out.append(max(highs[j] for j in window) if fn == "donchian_high" else min(lows[j] for j in window))
        return out
    if fn == "atr_breakout_level":  # prev_close + k*ATR
        atr = _atr(bars, int(p("period", 14))); k = p("k", 1.5); pc = _shift(close, 1)
        return [(pc[i] + k * atr[i]) if (atr[i] is not None and pc[i] is not None) else None for i in range(len(bars))]
    if fn in ("keltner_upper", "keltner_mid"):
        ema = _ema(close, int(p("ema_period", 20))); atr = _atr(bars, int(p("atr_period", 10))); mult = p("mult", 2.0)
        if fn == "keltner_mid":
            return ema
        return [(e + mult * a) if (e is not None and a is not None) else None for e, a in zip(ema, atr)]
    if fn in ("supertrend_dir", "supertrend_line"):
        return _supertrend(bars, int(p("atr_period", 10)), p("multiplier", 3.0), fn)
    if fn == "roc":
        return _roc(close, int(p("period", 30)))
    if fn in ("stoch_k", "stoch_d"):
        return _stoch(bars, int(p("k_period", 14)), int(p("smooth", 3)), int(p("d_period", 3)), fn)
    if fn == "vwap":
        return _vwap(bars, int(p("period", 20)))
    if fn in ("vwap_lower", "vwap_upper"):
        return _vwap_band(bars, int(p("period", 20)), p("sigma", 2.0), fn == "vwap_upper")
    raise ValueError(f"unknown indicator fn '{fn}'")


def _supertrend(bars, atr_period, mult, want):
    close = _col(bars, "close"); atr = _atr(bars, atr_period)
    n = len(bars); line = [None] * n; direction = [None] * n
    prev_line = None; prev_dir = 1
    for i in range(n):
        if atr[i] is None:
            continue
        hl2 = (float(bars[i][2]) + float(bars[i][3])) / 2
        upper = hl2 + mult * atr[i]; lower = hl2 - mult * atr[i]
        if prev_line is None:
            prev_line = lower; prev_dir = 1
        else:
            if prev_dir == 1:
                cur = max(lower, prev_line)
                if close[i] < cur:
                    prev_dir = -1; cur = upper
            else:
                cur = min(upper, prev_line)
                if close[i] > cur:
                    prev_dir = 1; cur = lower
            prev_line = cur
        line[i] = prev_line; direction[i] = prev_dir
    return direction if want == "supertrend_dir" else line


# ------------------------------- evaluation -------------------------------- #
def _resolve_num(v, params):
    if isinstance(v, str) and v.startswith("$"):
        return params.get(v[1:])
    return v


def _operand_series(ref, series, bars, params):
    """Return a full-length series for an operand ref."""
    if isinstance(ref, (int, float)):
        return [float(ref)] * len(bars)
    if isinstance(ref, str):
        if ref.startswith("$"):
            val = params.get(ref[1:])
            return [float(val) if val is not None else None] * len(bars)
        if ref in _PRICE_IDX:
            return _col(bars, ref)
        if ref == "prev_close":
            return _shift(_col(bars, "close"), 1)
        if ref in series:
            return series[ref]
    raise ValueError(f"unknown operand '{ref}'")


def _last_two(s):
    valid = [(i, v) for i, v in enumerate(s) if v is not None]
    if len(valid) < 2:
        return None, None
    return valid[-2][1], valid[-1][1]


def _cond(c, series, bars, params):
    op = c["op"]
    lhs = _operand_series(c["lhs"], series, bars, params)
    rhs = _operand_series(c.get("rhs", 0), series, bars, params)
    lp, lc = _last_two(lhs); rp, rc = _last_two(rhs)
    if lc is None or rc is None:
        return False
    if op == "cross_above":
        return lp is not None and rp is not None and lp <= rp and lc > rc
    if op == "cross_below":
        return lp is not None and rp is not None and lp >= rp and lc < rc
    if op == "gt":
        return lc > rc
    if op == "lt":
        return lc < rc
    if op == "gte":
        return lc >= rc
    if op == "lte":
        return lc <= rc
    if op == "rising":
        return lp is not None and lc > lp
    if op == "falling":
        return lp is not None and lc < lp
    raise ValueError(f"unknown op '{op}'")


def evaluate(spec: dict, bars: list, params: dict) -> DeclSignal:
    """Compute indicators and evaluate AND-ed entry / exit condition lists on the latest bar."""
    if not bars or len(bars) < 30:
        return DeclSignal(reason="insufficient bars")
    series: dict = {}
    for name, ispec in (spec.get("indicators") or {}).items():
        series[name] = _build(name, ispec, bars, params)
    entry = all(_cond(c, series, bars, params) for c in (spec.get("entry") or [])) and bool(spec.get("entry"))
    exit_ = any(_cond(c, series, bars, params) for c in (spec.get("exit") or []))
    latest = {k: (round(v[-1], 6) if v and v[-1] is not None else None) for k, v in series.items()}
    reason = spec.get("entry_reason", "declarative entry") if entry else ""
    return DeclSignal(entry=entry, exit=exit_, reason=reason, indicators=latest)


# ---------------- capability surface + spec validator (Import Pipeline P2) ---------------- #
# Required numeric params per indicator fn (used to validate imported declarative specs).
SUPPORTED_FNS: dict[str, list[str]] = {
    "ema": ["period"], "sma": ["period"], "rsi": ["period"], "atr": ["period"],
    "macd_line": ["fast", "slow"], "macd_signal": ["fast", "slow", "signal"],
    "macd_hist": ["fast", "slow", "signal"],
    "bb_lower": ["period", "std"], "bb_upper": ["period", "std"], "bb_mid": ["period"],
    "donchian_high": ["period"], "donchian_low": ["period"],
    "atr_breakout_level": ["period", "k"],
    "keltner_upper": ["ema_period", "atr_period", "mult"], "keltner_mid": ["ema_period"],
    "supertrend_dir": ["atr_period", "multiplier"], "supertrend_line": ["atr_period", "multiplier"],
    "roc": ["period"],
    "stoch_k": ["k_period", "d_period", "smooth"], "stoch_d": ["k_period", "d_period", "smooth"],
    "vwap": ["period"], "vwap_lower": ["period", "sigma"], "vwap_upper": ["period", "sigma"],
}
SUPPORTED_OPS: set[str] = {"cross_above", "cross_below", "gt", "lt", "gte", "lte", "rising", "falling"}


def _operand_valid(ref, indicator_ids: set) -> bool:
    if isinstance(ref, (int, float)):
        return True
    if isinstance(ref, str):
        if ref.startswith("$"):
            return len(ref) > 1
        return ref in _PRICE_IDX or ref == "prev_close" or ref in indicator_ids
    return False


def validate_spec(spec: dict) -> dict:
    """Deterministically verify a declarative spec compiles against THIS engine's primitives.
    Returns {ok, issues:[str]} — used to gate imported strategies as executable/wireable."""
    issues: list[str] = []
    if not isinstance(spec, dict):
        return {"ok": False, "issues": ["spec is not an object"]}
    indicators = spec.get("indicators") or {}
    if not isinstance(indicators, dict):
        issues.append("indicators must be an object")
        indicators = {}
    ids = set(indicators.keys())
    for iid, ispec in indicators.items():
        if not isinstance(ispec, dict) or "fn" not in ispec:
            issues.append(f"indicator '{iid}' missing fn")
            continue
        fn = ispec.get("fn")
        if fn not in SUPPORTED_FNS:
            issues.append(f"unsupported indicator fn '{fn}' (id '{iid}')")
            continue
        for req in SUPPORTED_FNS[fn]:
            if req not in ispec:
                issues.append(f"indicator '{iid}' ({fn}) missing param '{req}'")
    entry = spec.get("entry") or []
    exit_ = spec.get("exit") or []
    if not isinstance(entry, list) or not entry:
        issues.append("entry must be a non-empty list of conditions")
        entry = entry if isinstance(entry, list) else []
    for grp, conds in (("entry", entry), ("exit", exit_ if isinstance(exit_, list) else [])):
        for j, c in enumerate(conds):
            if not isinstance(c, dict) or "op" not in c or "lhs" not in c:
                issues.append(f"{grp}[{j}] missing op/lhs")
                continue
            if c["op"] not in SUPPORTED_OPS:
                issues.append(f"{grp}[{j}] unsupported op '{c['op']}'")
            if not _operand_valid(c.get("lhs"), ids):
                issues.append(f"{grp}[{j}] invalid lhs operand '{c.get('lhs')}'")
            if "rhs" in c and not _operand_valid(c.get("rhs"), ids):
                issues.append(f"{grp}[{j}] invalid rhs operand '{c.get('rhs')}'")
    return {"ok": len(issues) == 0, "issues": issues}
