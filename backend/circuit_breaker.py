"""
circuit_breaker.py — SECONDARY defensive layer (tri-state PASS / CAUTION / VETO).

The Hunter (primary technical layer) is the SOLE trade driver. This layer never
scores or co-decides; it only ever DOWNGRADES, and only a VETO blocks.

States
------
* PASS    — no meaningful contradiction. Proceed.
* CAUTION — moderate concern (e.g. bearish macro / negative news). Trade proceeds
            NORMALLY at full size; the state is logged for later analysis only.
* VETO    — reserved STRICTLY for existential threats (exchange insolvency,
            protocol exploit, regulatory shutdown, catastrophic market event).

CONSTRAINT (hard rule): sentiment-based bearishness, macro headwinds, or
"hawkish Fed" talk are CATEGORICALLY FORBIDDEN from triggering a VETO. They may
produce at most CAUTION. The ONLY path to VETO is an explicit existential event
supplied by a future event-classifier/feed (`existential_event`). Until that
exists, VETO never fires from this module — by design it is extremely rare.
"""
from __future__ import annotations

PASS = "PASS"
CAUTION = "CAUTION"
VETO = "VETO"

# news_sentiment below this (when a numeric news score is wired) → CAUTION.
CAUTION_NEWS_FLOOR = -0.2


def evaluate_breaker(
    macro_bias: str,
    macro_confidence: float,
    news_sentiment: float | None = None,
    existential_event: str | None = None,
) -> tuple[str, str]:
    """Return (state, reason).

    `existential_event` is the ONLY input that can yield VETO — it is the single
    plug-in point for a future hack/insolvency/regulatory-shutdown detector.
    Everything else degrades to CAUTION (non-blocking) or PASS.
    """
    if existential_event:
        return VETO, f"VETO_EXISTENTIAL:{existential_event}"

    if macro_bias == "BEARISH":
        return CAUTION, f"CAUTION_BEARISH_MACRO@{macro_confidence:.2f}"
    if news_sentiment is not None and news_sentiment < CAUTION_NEWS_FLOOR:
        return CAUTION, f"CAUTION_NEGATIVE_NEWS@{news_sentiment:.2f}"
    return PASS, "PASS"
