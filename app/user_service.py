"""
user_service.py
---------------
CRUD helpers for the `users` table.
"""

from __future__ import annotations

from datetime import datetime
from app.database import get_db


def register_or_update_user(email: str, interests: str) -> None:
    with get_db() as (_, cursor):
        cursor.execute(
            """
            INSERT INTO users (user_email, interests, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_email) DO UPDATE SET
                interests  = excluded.interests,
                updated_at = excluded.updated_at
            """,
            (email.strip().lower(), interests.strip(), datetime.now().isoformat()),
        )


def get_all_users() -> list[tuple[str, str]]:
    with get_db() as (_, cursor):
        cursor.execute("SELECT user_email, interests FROM users")
        return [(row["user_email"], row["interests"]) for row in cursor.fetchall()]


def get_user(email: str) -> dict | None:
    with get_db() as (_, cursor):
        cursor.execute(
            "SELECT user_email, interests, updated_at FROM users WHERE user_email = ?",
            (email.strip().lower(),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
