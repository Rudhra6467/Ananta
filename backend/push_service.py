"""Expo push notification service (mobile).

Stores device push tokens in Mongo (`push_tokens` collection) and broadcasts
event alerts to the Expo push API. Single-operator app, so every alert broadcasts
to all registered devices.

NOTE: Push delivery only works on a published / development build with Firebase
(`google-services.json`) configured — it is a no-op in Expo Go and web preview.
All sends are best-effort and never raise into the trading engine.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger("ananta.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

EVENT_TITLES = {
    "trade_opened": "Trade Opened",
    "trade_closed": "Trade Closed",
    "stop_loss": "Stop-Loss Hit",
    "trailing_stop": "Trailing Stop Armed",
    "kill_switch": "Kill Switch Triggered",
    "system_offline": "System Offline",
}


async def register_push_token(db, push_token: str, platform: str = "unknown") -> None:
    if not push_token:
        return
    await db.push_tokens.update_one(
        {"_id": push_token},
        {"$set": {"platform": platform, "updated_at": datetime.now(UTC).isoformat()}},
        upsert=True,
    )


async def _registered_tokens(db) -> list[str]:
    cursor = db.push_tokens.find({}, {"_id": 1})
    return [doc["_id"] async for doc in cursor]


async def send_push_event(db, event_type: str, message: str) -> dict:
    """Broadcast an event alert to all registered devices. Best-effort."""
    title = EVENT_TITLES.get(event_type, "Ananta Alert")
    try:
        tokens = await _registered_tokens(db)
    except Exception as e:  # pragma: no cover — DB hiccup must not crash callers
        logger.warning("push: token lookup failed: %s", e)
        return {"sent": 0, "error": "token_lookup_failed"}

    if not tokens:
        logger.info("push: no registered devices for event %s", event_type)
        return {"sent": 0}

    messages = [
        {"to": t, "title": title, "body": message, "sound": "default", "priority": "high",
         "data": {"event_type": event_type}}
        for t in tokens
    ]
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        logger.info("push: dispatched %s to %d device(s) [%s]", event_type, len(tokens), resp.status_code)
        return {"sent": len(tokens), "status": resp.status_code}
    except Exception as e:  # pragma: no cover — network failure must not crash callers
        logger.warning("push: dispatch failed for %s: %s", event_type, e)
        return {"sent": 0, "error": str(e)}
