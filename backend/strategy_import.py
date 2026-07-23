"""Strategy Import Pipeline (P2) — framework adapters, format detection, deterministic
validation, and mapping of an AI-extracted strategy into Ananta's internal library schema.

DESIGN — pluggable adapters
---------------------------
Each supported framework is a small `FrameworkAdapter` registered in `ADAPTERS`. To add a
new framework later (e.g. Backtrader, NautilusTrader) you register ONE adapter with a
`detect()` heuristic + a short `ai_hint` — no changes to the pipeline, endpoints or UI.

The heavy lifting (understanding arbitrary code) is done by the AI extractor in
`import_ai.py`; adapters only (a) auto-detect the most likely framework and (b) feed the
model a framework-specific hint so the extraction is grounded.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable


@dataclass
class FrameworkAdapter:
    key: str
    label: str
    ai_hint: str
    # returns a 0..1 confidence that `raw` is written in this framework
    detector: Callable[[str], float]
    file_hints: list[str] = field(default_factory=list)

    def detect(self, raw: str) -> float:
        try:
            return max(0.0, min(1.0, float(self.detector(raw or ""))))
        except Exception:  # noqa: BLE001
            return 0.0


def _score(patterns: list[str], raw: str, cap: float = 1.0) -> float:
    low = raw.lower()
    hits = sum(1 for p in patterns if re.search(p, low))
    if not patterns:
        return 0.0
    return min(cap, hits / max(2, len(patterns) * 0.6))


# ---------------- framework detectors ----------------
def _detect_pine(raw: str) -> float:
    s = 0.0
    if re.search(r"//@version\s*=\s*\d", raw):
        s += 0.7
    s += _score([r"\bstrategy\s*\(", r"\bindicator\s*\(", r"\bstrategy\.entry",
                 r"\bstrategy\.close", r"\bta\.", r"\bplotshape\b", r"\binput\.\w+\("], raw, cap=0.5)
    return min(1.0, s)


def _detect_freqtrade(raw: str) -> float:
    return _score([r"class\s+\w+\s*\(\s*istrategy\s*\)", r"from\s+freqtrade", r"populate_entry_trend",
                   r"populate_exit_trend", r"populate_indicators", r"minimal_roi", r"stoploss\s*=",
                   r"informative_pairs", r"dataframe\.loc"], raw)


def _detect_jesse(raw: str) -> float:
    return _score([r"from\s+jesse", r"class\s+\w+\s*\(\s*strategy\s*\)", r"def\s+should_long",
                   r"def\s+should_short", r"def\s+go_long", r"def\s+go_short", r"self\.buy\s*=",
                   r"self\.sell\s*=", r"def\s+update_position"], raw)


def _detect_json(raw: str) -> float:
    t = (raw or "").strip()
    if t.startswith("{") and t.endswith("}"):
        return 0.9
    if t.startswith("[") and t.endswith("]"):
        return 0.6
    return 0.0


ADAPTERS: dict[str, FrameworkAdapter] = {
    "pine_script": FrameworkAdapter(
        key="pine_script", label="Pine Script (TradingView)",
        ai_hint=("This is TradingView Pine Script. `strategy.entry`/`strategy.close`/`strategy.exit` define "
                 "orders; `ta.*` are indicators; `input.*` are tunable parameters; `//@version` marks the "
                 "dialect. `strategy.entry(..., strategy.short)` indicates short support."),
        detector=_detect_pine, file_hints=[".pine"]),
    "freqtrade": FrameworkAdapter(
        key="freqtrade", label="Freqtrade (Python)",
        ai_hint=("This is a Freqtrade IStrategy. `populate_entry_trend`/`populate_exit_trend` set entry/exit "
                 "signals on the dataframe; `minimal_roi` and `stoploss` define risk; `timeframe` sets the TF; "
                 "`can_short`/enter_short columns indicate short support; class attributes are parameters."),
        detector=_detect_freqtrade, file_hints=[".py"]),
    "jesse": FrameworkAdapter(
        key="jesse", label="Jesse (Python)",
        ai_hint=("This is a Jesse Strategy class. `should_long`/`should_short` are entry gates; "
                 "`go_long`/`go_short` place orders and set stop/take-profit; `update_position` manages exits; "
                 "the presence of short methods indicates short support; hyperparameters() are parameters."),
        detector=_detect_jesse, file_hints=[".py"]),
    "json": FrameworkAdapter(
        key="json", label="Generic JSON",
        ai_hint=("This is a generic JSON strategy definition. Map its fields (entry/exit/indicators/params/"
                 "risk/timeframe/direction) onto Ananta's schema, inferring anything not explicitly present."),
        detector=_detect_json, file_hints=[".json"]),
}

SUPPORTED_FORMATS = [{"key": a.key, "label": a.label} for a in ADAPTERS.values()] + [
    {"key": "auto", "label": "Auto-detect"},
]


def detect_format(raw: str) -> dict:
    """Return {best, scores:{key:score}} for the raw source."""
    scores = {k: round(a.detect(raw), 3) for k, a in ADAPTERS.items()}
    best = max(scores, key=scores.get) if scores else "json"
    if scores.get(best, 0) < 0.15:
        best = "json" if _detect_json(raw) > 0 else "pine_script"
    return {"best": best, "scores": scores}


def ai_hint_for(fmt: str) -> str:
    a = ADAPTERS.get(fmt)
    return a.ai_hint if a else "Infer the framework from the code and map it onto Ananta's schema."


# ---------------- deterministic post-validation ----------------
_ALLOWED_CATEGORIES = {
    "Trend Following", "Momentum", "Mean Reversion", "Volatility",
    "Statistical / Quantitative", "Academic / Institutional", "Breakout", "Scalping",
}
_ALLOWED_RISK = {"Conservative", "Moderate", "Aggressive"}


def _issue(severity: str, message: str) -> dict:
    return {"severity": severity, "message": message}


def validate_extraction(ex: dict) -> dict:
    """Deterministic guardrails layered on top of the AI's own conversion report.
    severity: error (blocks nothing but flagged red) | warning | info."""
    issues: list[dict] = []
    entry = ex.get("entry_rules") or []
    exit_ = ex.get("exit_rules") or []
    params = ex.get("parameters") or {}
    direction = (ex.get("direction") or "long").lower()

    if not entry:
        issues.append(_issue("error", "No entry conditions could be extracted — the strategy cannot trade without them."))
    if not exit_:
        issues.append(_issue("warning", "No explicit exit rules found — Ananta's universal exit engine defaults will be applied."))
    if not params:
        issues.append(_issue("warning", "No tunable parameters detected — the strategy will run with fixed logic only."))
    if not (ex.get("risk_management") or {}):
        issues.append(_issue("warning", "No risk-management block found — a default stop-loss will be required before live trading."))

    if direction in ("short", "both"):
        issues.append(_issue("warning",
            "Short-selling detected. Ananta's live engine is long-only spot today; short signals are "
            "stored but ignored during paper/live execution until short support ships."))

    mtype = ex.get("market_type") or ["Crypto"]
    if "Crypto" not in mtype:
        issues.append(_issue("info", f"Designed for {', '.join(mtype)} — Ananta trades Crypto spot; behaviour may differ."))

    cat = ex.get("category")
    if cat and cat not in _ALLOWED_CATEGORIES:
        issues.append(_issue("info", f"Category '{cat}' normalised to the closest supported family."))

    for ind in ex.get("indicators") or []:
        nm = (ind.get("name") if isinstance(ind, dict) else str(ind)) or ""
        if re.search(r"order.?book|depth|level\s*2|l2|funding|open.?interest|tick", nm, re.I):
            issues.append(_issue("warning", f"Indicator '{nm}' needs data Ananta may not stream on all timeframes — verify before live use."))

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    status = "blocked" if errors else "review" if warnings else "ready"
    return {"issues": issues, "status": status,
            "error_count": len(errors), "warning_count": len(warnings)}


# ---------------- map AI extraction -> library schema ----------------
_GRADE = [(85, "A"), (70, "B"), (55, "C"), (40, "D")]


def _grade(score: int) -> str:
    for lo, g in _GRADE:
        if score >= lo:
            return g
    return "E"


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "imported").lower()).strip("-") or "imported"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:  # noqa: BLE001
        return default


def validate_declarative(decl: dict) -> dict:
    """Validate the AI-extracted declarative block against the live engine's primitives.
    Returns {compilable, params, spec, issues}. compilable=True only when the spec both
    claims compilable AND passes the deterministic engine validator."""
    from declarative_engine import validate_spec  # local import avoids cycle at module load

    decl = decl if isinstance(decl, dict) else {}
    params = decl.get("params") or {}
    spec = {
        "indicators": decl.get("indicators") or {},
        "entry": decl.get("entry") or [],
        "exit": decl.get("exit") or [],
        "entry_reason": decl.get("entry_reason") or "Imported strategy entry",
    }
    if not isinstance(params, dict):
        params = {}
    # coerce param values to numbers where possible
    clean_params = {}
    for k, v in params.items():
        try:
            fv = float(v)
            clean_params[k] = int(fv) if float(fv).is_integer() else fv
        except (TypeError, ValueError):
            continue
    res = validate_spec(spec)
    ai_claim = bool(decl.get("compilable"))
    compilable = ai_claim and res["ok"] and bool(spec["entry"])
    issues = list(res["issues"])
    if ai_claim and not res["ok"]:
        issues.insert(0, "AI marked this compilable but the rules do not map to supported primitives.")
    return {"compilable": compilable, "params": clean_params, "spec": spec,
            "issues": issues, "reason": decl.get("reason") or ""}


def build_draft(*, raw_source: str, source_format: str, detected: dict,
                extraction: dict, name_override: str | None = None) -> dict:
    """Compose a draft document (persisted in `strategy_imports`) from the AI extraction.
    The draft mirrors the library schema (so review/edit uses the same fields) plus import
    provenance + validation. `approve` later copies the library fields into strategy_library."""
    ex = extraction or {}
    if not isinstance(ex, dict):
        ex = {}
    now = datetime.now(UTC).isoformat()
    name = str(name_override or ex.get("name") or "Imported Strategy").strip() or "Imported Strategy"
    health = _clamp(ex.get("ai_health_score"), 0, 100, 55)
    conf = _clamp(ex.get("ai_confidence"), 0, 100, 60)
    conv = ex.get("conversion") if isinstance(ex.get("conversion"), dict) else {}
    conv_conf = _clamp(conv.get("confidence_score"), 0, 100, conf)
    validation = validate_extraction(ex)
    decl = validate_declarative(ex.get("declarative") or {})

    label = ADAPTERS.get(source_format).label if ADAPTERS.get(source_format) else source_format
    _tfs = ex.get("timeframes")
    if not isinstance(_tfs, list) or not _tfs:
        _tfs = ["1H"]
    tf = ex.get("timeframe") or _tfs[0]
    tf = str(tf) if tf is not None else "1H"

    return {
        "id": _slug(name),
        # --- library-shaped fields (editable in review) ---
        "name": name,
        "description": ex.get("description") or "",
        "source": f"Imported · {label}",
        "category": ex.get("category") or "Trend Following",
        "market_type": ex.get("market_type") or ["Crypto"],
        "style": ex.get("style") or ex.get("category") or "Trend Following",
        "ideal_market": ex.get("ideal_market") or "",
        "timeframe": tf,
        "timeframes": _tfs,
        "risk": ex.get("risk") if ex.get("risk") in _ALLOWED_RISK else "Moderate",
        "market_regimes": ex.get("market_regimes") or [],
        "entry_rules": ex.get("entry_rules") or [],
        "exit_rules": ex.get("exit_rules") or [],
        "risk_management": ex.get("risk_management") or {},
        "parameters": ex.get("parameters") or {},
        "ideal_conditions": ex.get("ideal_conditions") or [],
        "avoid_conditions": ex.get("avoid_conditions") or [],
        "historical_results": {"roi": 0, "win_rate": 0, "profit_factor": 0, "sharpe": 0,
                               "sortino": 0, "max_drawdown": 0, "avg_trade": 0, "trade_count": 0},
        "ai_summary": ex.get("ai_summary") or "",
        "ai_health_score": health,
        "ai_grade": _grade(health),
        "ai_confidence": conf,
        "recommended_market": ex.get("recommended_market") or "Crypto majors",
        "rating": max(1, min(5, round(health / 20))),
        "favorite": False,
        "internal": False,
        "engine_key": None,
        # --- import-specific metadata ---
        "imported": True,
        "backtested": False,
        "source_format": source_format,
        "source_label": label,
        "detected": detected,
        "direction": (ex.get("direction") or "long").lower(),
        "long_short_support": ex.get("long_short_support") or {"long": True, "short": False},
        "indicators": ex.get("indicators") or [],
        "position_sizing": ex.get("position_sizing") or {},
        "volatility_preference": ex.get("volatility_preference") or "Any",
        "expected_holding_period": ex.get("expected_holding_period") or "",
        "strengths": ex.get("strengths") or [],
        "weaknesses": ex.get("weaknesses") or [],
        "tags": ex.get("tags") or [],
        "conversion_confidence": conv_conf,
        "conversion_report": conv.get("notes") or "",
        "conversion_unsupported": conv.get("unsupported_features") or [],
        "conversion_missing": conv.get("missing_logic") or [],
        "conversion_warnings": conv.get("warnings") or [],
        "validation": validation,
        # --- declarative compilation (P2: imported → executable) ---
        "declarable": decl["compilable"],
        "declarative_spec": decl["spec"],
        "engine_params": decl["params"],
        "declarative_issues": decl["issues"],
        "declarative_reason": decl["reason"],
        "raw_source": (raw_source or "")[:20000],
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }


# library_seed schema fields that get copied verbatim on approve
LIBRARY_FIELDS = [
    "id", "name", "description", "source", "category", "market_type", "style", "ideal_market",
    "timeframe", "timeframes", "risk", "market_regimes", "entry_rules", "exit_rules",
    "risk_management", "parameters", "ideal_conditions", "avoid_conditions", "historical_results",
    "ai_summary", "ai_health_score", "ai_grade", "ai_confidence", "recommended_market", "rating",
    "favorite", "internal", "engine_key",
    # keep import provenance in the library so the catalog can badge it
    "imported", "backtested", "source_format", "source_label", "direction",
    "long_short_support", "indicators", "position_sizing", "volatility_preference",
    "expected_holding_period", "strengths", "weaknesses", "tags",
    "conversion_confidence", "conversion_report", "validation",
    "declarable", "declarative_spec", "engine_params",
]


def to_library_doc(draft: dict) -> dict:
    """Project a reviewed/edited draft into a library document ready for strategy_library."""
    now = datetime.now(UTC).isoformat()
    doc = {k: draft.get(k) for k in LIBRARY_FIELDS}
    doc["ai_grade"] = _grade(_clamp(doc.get("ai_health_score"), 0, 100, 55))
    doc["rating"] = max(1, min(5, round(_clamp(doc.get("ai_health_score"), 0, 100, 55) / 20)))
    doc["created_at"] = now
    doc["updated_at"] = now
    return doc
