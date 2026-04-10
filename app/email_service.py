"""
email_service.py
----------------
Sends personalised HTML recommendation emails via SMTP.

Bug fixed: the original `fetch_event_details()` looped over event_ids and
issued one SELECT per event — O(N) queries.  This version fetches all events
in a single `WHERE event_id IN (...)` query.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.database import get_db
from app.config import SENDER_EMAIL, SENDER_PASSWORD, SMTP_HOST, SMTP_PORT
from app.logger import logger


def fetch_events_by_ids(event_ids: list[str]) -> list[dict]:
    """Fetch title/description/link for multiple events in one query."""
    if not event_ids:
        return []

    placeholders = ",".join("?" * len(event_ids))
    with get_db() as (_, cursor):
        cursor.execute(
            f"SELECT event_id, title, description, link FROM events WHERE event_id IN ({placeholders})",
            event_ids,
        )
        # Preserve the original ordering supplied by the recommender
        rows = {row["event_id"]: dict(row) for row in cursor.fetchall()}

    return [rows[eid] for eid in event_ids if eid in rows]


def _build_html(events: list[dict]) -> str:
    rows_html = "".join(
        f"""
        <tr>
          <td style="padding:12px 0; border-bottom:1px solid #eee;">
            <b style="font-size:15px;">{e['title']}</b><br>
            <span style="color:#555; font-size:13px;">{(e.get('description') or '')[:160]}…</span><br>
            <a href="{e.get('link','#')}"
               style="color:#4F46E5; font-size:13px; text-decoration:none;">
               → View & Register
            </a>
          </td>
        </tr>
        """
        for e in events
    )
    return f"""
    <html><body style="font-family:Arial,sans-serif; max-width:600px; margin:auto; color:#222;">
      <h2 style="color:#4F46E5;">🎓 Events Picked For You</h2>
      <p>Based on your interests, here are this week's top picks:</p>
      <table width="100%" cellpadding="0" cellspacing="0">{rows_html}</table>
      <p style="font-size:12px; color:#aaa; margin-top:24px;">
        You're receiving this because you registered on VIT Event Recommender.
      </p>
    </body></html>
    """


def send_email(user_email: str, event_ids: list[str]) -> bool:
    """
    Send a recommendation email.  Returns True on success, False on failure.
    Raises ValueError if email credentials are not configured.
    """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        raise ValueError(
            "Email credentials missing. Set SENDER_EMAIL and SENDER_PASSWORD in .env"
        )

    events = fetch_events_by_ids(event_ids)
    if not events:
        logger.warning("No events found for ids %s — skipping email to %s", event_ids, user_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER_EMAIL
    msg["To"] = user_email
    msg["Subject"] = "🎓 Your Personalised VIT Event Recommendations"
    msg.attach(MIMEText(_build_html(events), "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        logger.info("Email sent to %s (%d events).", user_email, len(events))
        return True
    except smtplib.SMTPException as exc:
        logger.error("Failed to send email to %s: %s", user_email, exc)
        return False
