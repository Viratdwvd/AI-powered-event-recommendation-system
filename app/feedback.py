"""
feedback.py
-----------
Saves and retrieves user feedback (ratings) for events.
Was an empty stub in the original codebase.
"""

from __future__ import annotations

from app.database import get_db


def save_feedback(user_email: str, event_id: str, rating: int) -> None:
    """Upsert a 1–5 star rating for an event."""
    if rating not in range(1, 6):
        raise ValueError(f"Rating must be 1–5, got {rating!r}")

    with get_db() as (_, cursor):
        cursor.execute(
            """
            INSERT INTO feedback (user_email, event_id, rating)
            VALUES (?, ?, ?)
            ON CONFLICT(user_email, event_id) DO UPDATE SET rating = excluded.rating
            """,
            (user_email, event_id, rating),
        )


def get_user_feedback(user_email: str) -> list[dict]:
    """Return all ratings a user has submitted."""
    with get_db() as (_, cursor):
        cursor.execute(
            "SELECT event_id, rating FROM feedback WHERE user_email = ?",
            (user_email,),
        )
        return [dict(row) for row in cursor.fetchall()]
