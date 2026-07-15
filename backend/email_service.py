"""Resend transactional email (waitlist notifications).

Fire-and-forget by design: a mail failure must NEVER break the waitlist flow, so
every send swallows its own errors and logs them. No-op when RESEND_API_KEY is
absent (keeps local/dev + misconfigured deploys running).
"""
from __future__ import annotations

import asyncio
import logging
import os

import resend

logger = logging.getLogger(__name__)

_BRAND = "#00E5CC"
_BG = "#0B0D10"


def _configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("SENDER_EMAIL"))


async def _send(to: str, subject: str, html: str) -> bool:
    """Send one email off the event loop. Returns True on success, False otherwise."""
    if not _configured():
        logger.info("Resend not configured — skipping email to %s", to)
        return False
    resend.api_key = os.environ["RESEND_API_KEY"]
    params = {"from": os.environ["SENDER_EMAIL"], "to": [to], "subject": subject, "html": html}
    try:
        res = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Sent email to %s (id=%s)", to, (res or {}).get("id"))
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to)
        return False


def _shell(title: str, body_html: str) -> str:
    return f"""
    <div style="background:{_BG};padding:32px 0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0"
                 style="background:#121418;border:1px solid #2A2D35;border-radius:14px;overflow:hidden;">
            <tr><td style="padding:26px 30px 8px;">
              <div style="color:{_BRAND};font-weight:800;letter-spacing:3px;font-size:12px;">ANANTA</div>
              <h1 style="color:#E2E4E9;font-size:20px;font-weight:600;margin:12px 0 0;">{title}</h1>
            </td></tr>
            <tr><td style="padding:12px 30px 28px;color:#A7ACB5;font-size:14px;line-height:22px;">
              {body_html}
            </td></tr>
          </table>
          <div style="color:#5A5F68;font-size:11px;margin-top:16px;">Ananta · Algorithmic Trading OS</div>
        </td></tr>
      </table>
    </div>
    """


async def notify_owner_new_lead(name: str, email: str, feature: str | None, platform: str | None) -> None:
    to = os.environ.get("WAITLIST_NOTIFY_EMAIL")
    if not to:
        return
    ctx = "".join(
        f'<tr><td style="color:#5A5F68;padding:3px 0;">{k}</td>'
        f'<td style="color:#E2E4E9;padding:3px 0;text-align:right;">{v}</td></tr>'
        for k, v in [("Name", name), ("Email", email),
                     ("Feature", feature or "—"), ("Platform", platform or "—")]
    )
    body = (
        f"<p>A new visitor joined the Ananta waitlist.</p>"
        f'<table width="100%" style="font-size:13px;margin-top:8px;">{ctx}</table>'
        f'<p style="margin-top:18px;">Review &amp; approve them from the Workspace → Access Requests panel.</p>'
    )
    await _send(to, f"New Ananta waitlist request — {name}", _shell("New waitlist request", body))


async def notify_user_decision(name: str, email: str, approved: bool) -> None:
    if approved:
        body = (
            f"<p>Hi {name or 'there'},</p>"
            f"<p>Great news — your request for early access to <strong>Ananta</strong> has been "
            f"approved. We'll follow up shortly with next steps to get you set up.</p>"
            f"<p>Thanks for your interest in trading with evidence, not assumptions.</p>"
        )
        subj = "You're approved for Ananta early access"
        title = "You're in"
    else:
        body = (
            f"<p>Hi {name or 'there'},</p>"
            f"<p>Thanks for your interest in <strong>Ananta</strong>. We aren't able to offer you "
            f"access at this time, but we've kept you on our list and will reach out as capacity opens up.</p>"
        )
        subj = "Update on your Ananta access request"
        title = "Access update"
    await _send(email, subj, _shell(title, body))
