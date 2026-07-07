"""AI Quant Analyst — plain-English Q&A over the trading engine's own reasoning logs,
trade ledger and analytics. Uses the Emergent LLM key via emergentintegrations.

The analyst is grounded: it only sees a compact snapshot of the app's real data that we
assemble here, so answers stay factual instead of hallucinated. Multi-turn is supported by
persisting each turn in `ai_analyst_messages` and replaying a short transcript per request.
"""
import os
import logging
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("ananta.ai_analyst")

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-6"
HISTORY_TURNS = 6  # prior (user+assistant) pairs replayed for continuity

SYSTEM_PROMPT = (
    "You are Ananta's AI Quant Analyst — a sharp, concise institutional trading analyst embedded "
    "in an algorithmic crypto trading dashboard. You answer the operator's plain-English questions "
    "using ONLY the DATA SNAPSHOT provided in each message (reasoning log, closed trades, analytics). "
    "Rules:\n"
    "- Be specific and cite the actual numbers/symbols/strategies from the data.\n"
    "- If the data is insufficient to answer, say so plainly and state what's missing — never invent trades or metrics.\n"
    "- Keep it tight: 2–5 short sentences or a few bullets. No preamble, no disclaimers about being an AI.\n"
    "- When useful, point out patterns (which strategy/exit_reason/regime drove wins or losses)."
)


def _fmt_reasoning(items: list[dict]) -> str:
    lines = []
    for r in items:
        ts = str(r.get("timestamp", ""))[:19]
        dec = r.get("decision", "?")
        blocked = r.get("blocked_reasons") or []
        b = f" blocked={','.join(blocked)}" if blocked else ""
        lines.append(f"- {ts} {r.get('symbol','?')} decision={dec} conf={r.get('confidence','?')} bias={r.get('bias','?')}{b} :: {str(r.get('reason',''))[:160]}")
    return "\n".join(lines) if lines else "(no reasoning entries)"


def _fmt_trades(items: list[dict]) -> str:
    lines = []
    for t in items:
        ts = str(t.get("timestamp", ""))[:19]
        pnl = t.get("pnl")
        ret = t.get("return_pct")
        lines.append(
            f"- {ts} {t.get('symbol','?')} {t.get('side','?')} strat={t.get('strategy','?')} "
            f"exit={t.get('exit_reason','-')} pnl={pnl if pnl is not None else '-'} "
            f"ret%={round(ret,2) if isinstance(ret,(int,float)) else '-'} "
            f"regime={t.get('volatility_regime','-')} grade={t.get('entry_quality_grade','-')}"
        )
    return "\n".join(lines) if lines else "(no closed trades yet)"


async def _gather_context(db) -> str:
    reasoning = await db.reasoning.find({}, {"_id": 0}).sort("timestamp", -1).limit(25).to_list(25)
    trades = await db.trades.find({"status": "CLOSED"}, {"_id": 0}).sort("timestamp", -1).limit(30).to_list(30)
    if not trades:
        trades = await db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(30).to_list(30)

    closed = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    total_pnl = round(sum((t.get("pnl") or 0) for t in closed), 2)
    win_rate = round(100 * len(wins) / len(closed), 1) if closed else 0.0

    summary = (
        f"AGGREGATE (last {len(closed)} closed trades): total_pnl=${total_pnl}, "
        f"win_rate={win_rate}%, wins={len(wins)}, losses={len(closed) - len(wins)}"
    )
    return (
        "DATA SNAPSHOT (generated " + datetime.now(timezone.utc).isoformat()[:19] + "):\n\n"
        f"{summary}\n\n"
        "RECENT CLOSED TRADES:\n" + _fmt_trades(trades) + "\n\n"
        "RECENT AI REASONING LOG:\n" + _fmt_reasoning(reasoning)
    )


async def answer_question(db, session_id: str, question: str) -> str:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    context = await _gather_context(db)

    # Replay a short transcript for continuity.
    prior = await db.ai_analyst_messages.find(
        {"session_id": session_id}, {"_id": 0, "role": 1, "content": 1}
    ).sort("ts", -1).limit(HISTORY_TURNS * 2).to_list(HISTORY_TURNS * 2)
    prior = list(reversed(prior))
    transcript = ""
    if prior:
        transcript = "\n\nPRIOR CONVERSATION:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content'][:400]}" for m in prior
        )

    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=SYSTEM_PROMPT,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)

    user_text = f"{context}{transcript}\n\nOPERATOR QUESTION: {question}"
    answer = await chat.send_message(UserMessage(text=user_text))

    now = datetime.now(timezone.utc)
    await db.ai_analyst_messages.insert_many([
        {"session_id": session_id, "role": "user", "content": question, "ts": now},
        {"session_id": session_id, "role": "assistant", "content": str(answer), "ts": now},
    ])
    return str(answer)
