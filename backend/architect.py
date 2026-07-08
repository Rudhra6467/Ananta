"""Ananta Strategy Architect — an AI quant strategist that interviews the user in plain
English and outputs a fully-validated, deployable strategy configuration.

Grounding & safety: our live engine has a FIXED set of built-in strategy families
(hunter / squeeze / continuation), each with a strict ParameterSchema. The Architect must map
the user's goal to the BEST-FIT built-in family and emit only params that exist in that family's
schema — so every design is immediately runnable in the Research Lab / validation / trading.
We inject the real schemas into the system prompt and re-validate the model's params server-side.
"""
import os
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage

from strategy import list_schemas, get_schema
from strategy.core import validate_params

logger = logging.getLogger("ananta.architect")

MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-6"


def _schema_catalogue() -> str:
    """Compact machine-readable catalogue of the built-in strategies + their editable params."""
    lines = []
    for s in list_schemas():
        dna = s.dna if isinstance(s.dna, dict) else {}
        lines.append(f"\n### {s.key} — {s.name} (v{s.version})")
        lines.append(f"purpose: {dna.get('purpose', s.description or '')}")
        lines.append(f"works_best: {dna.get('works_best', '?')} | avoid: {dna.get('avoid', '?')}")
        lines.append("params:")
        for p in s.params:
            rng = f" range {p.min}..{p.max}" if getattr(p, "min", None) is not None else ""
            opts = f" options {p.options}" if getattr(p, "options", None) else ""
            lines.append(f"  - {p.id} ({p.type}, group={p.group.value if hasattr(p.group,'value') else p.group}, default={p.default}{rng}{opts}) :: {p.label}")
    return "\n".join(lines)


SYSTEM_PROMPT_TEMPLATE = """You are the ANANTA STRATEGY ARCHITECT — an institutional quantitative strategist inside the Ananta Trading OS. You are NOT a chatbot. You convert a user's plain-English trading goals into a deployable Ananta strategy configuration. Every conversation must end with an executable strategy, never just advice.

You may ONLY design strategies on top of these built-in strategy families and their exact parameters. Map the user's goal to the BEST-FIT family and tune ONLY parameters that exist in that family's schema (respect the ranges/options). Do NOT invent indicators or parameters that are not listed.

AVAILABLE STRATEGIES & PARAMETER SCHEMAS:
{catalogue}

DISCOVERY: Ask only the MINIMUM questions needed (objective, risk tolerance, holding duration, style, automation). Ask ONE focused question at a time. Keep each question short with 3-5 tappable quick options when sensible. After AT MOST 4-5 exchanges (or immediately if the user's first message is already specific), produce the final design. If the user skips detail, choose conservative defaults.

OUTPUT PROTOCOL — you MUST respond with a SINGLE JSON object and nothing else:
- To ask a question:
  {{"phase":"question","message":"<one short question in plain English>","quick_replies":["opt1","opt2","opt3"]}}
- To deliver the final strategy:
  {{"phase":"design",
    "strategy_key":"<one of the family keys above>",
    "name":"<short human name, e.g. 'Hunter Conservative'>",
    "params":{{ <only valid params for that family, correctly typed> }},
    "card":{{
      "category":"<e.g. Trend Following>",
      "market":"<e.g. Bullish Crypto>",
      "risk":"<Low|Medium|High>",
      "confidence":<0-100 integer>,
      "suitable_for":["BTC","ETH"],
      "timeframes":["15m","1H","4H"],
      "logic_summary":"<2 sentences, plain English>",
      "expected_win_rate":"<e.g. 60-68%>",
      "expected_profit_factor":"<e.g. 1.7>",
      "expected_drawdown":"<e.g. 8%>",
      "strengths":["..."],
      "weaknesses":["..."],
      "failure_scenarios":["..."],
      "param_reasons":{{"<param_id>":"<why this value, plain English>"}}
    }}
  }}
Rules: Output ONLY the JSON (no markdown fences, no prose around it). Use plain English in all human-facing text. Keep arrays concise (max 4 items)."""


def _system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(catalogue=_schema_catalogue())


def _extract_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    # grab the outermost JSON object
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


async def architect_reply(session_id: str, history: list[dict], user_message: str) -> dict:
    """Run one Architect turn. `history` is prior [{role, content}] turns. Returns a dict with
    phase 'question' or 'design'. Design params are re-validated (clamped) against the schema."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    transcript = ""
    if history:
        transcript = "\n\nCONVERSATION SO FAR:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content'][:600]}" for m in history[-10:]
        )

    chat = LlmChat(api_key=api_key, session_id=session_id, system_message=_system_prompt()).with_model(MODEL_PROVIDER, MODEL_NAME)
    raw = await chat.send_message(UserMessage(text=f"{transcript}\n\nUSER: {user_message}\n\nRespond with the JSON object only."))

    try:
        data = _extract_json(str(raw))
    except Exception as e:  # noqa: BLE001
        logger.warning("architect JSON parse failed: %s", e)
        return {"phase": "question", "message": "Could you tell me a bit more about your goal (e.g. steady income, BTC breakouts, bear-market hedge)?", "quick_replies": []}

    if data.get("phase") == "design":
        key = data.get("strategy_key")
        schema = get_schema(key)
        if not schema:
            return {"phase": "question", "message": "Which market do you want to trade — crypto spot breakouts, dips, or continuation trends?", "quick_replies": ["Breakouts", "Buy dips", "Trend continuation"]}
        # keep only known params, coerce & validate/clamp against the schema
        valid_ids = {p.id: p for p in schema.params}
        cleaned = {}
        for pid, val in (data.get("params") or {}).items():
            p = valid_ids.get(pid)
            if not p:
                continue
            try:
                if p.type == "int":
                    val = int(val)
                elif p.type == "float":
                    val = float(val)
                elif p.type == "bool":
                    val = bool(val) if isinstance(val, bool) else str(val).lower() in ("true", "1", "yes", "on")
                if getattr(p, "min", None) is not None and isinstance(val, (int, float)):
                    val = max(p.min, min(p.max, val))
            except Exception:  # noqa: BLE001
                continue
            cleaned[pid] = val
        ok, errs = validate_params(schema, cleaned)
        if not ok:  # drop offenders rather than fail the whole design
            for msg in errs:
                for pid in list(cleaned):
                    if pid in msg:
                        cleaned.pop(pid, None)
        data["params"] = cleaned
        data["strategy_version"] = schema.version
        data["base_strategy_name"] = schema.name
    return data
