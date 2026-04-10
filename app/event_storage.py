"""
event_storage.py
----------------
Persists events (with embeddings) to SQLite.
Also tracks the last scrape metadata so the UI can show "last synced X ago".
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import numpy as np

from app.database import get_db
from app.embedder import generate_embedding, to_blob
from app.logger import logger


# ── Event upsert ─────────────────────────────────────────────────────────────

def save_events(events: list[dict[str, Any]]) -> int:
    saved = 0
    with get_db() as (_, cursor):
        for e in events:
            text      = f"{e['title']} {e.get('description','')} {e.get('category','')}"
            embedding = generate_embedding(text)
            blob      = to_blob(np.array(embedding, dtype="float32"))

            cursor.execute("""
                INSERT INTO events
                    (event_id, title, description, category, date, link, source, embedding)
                VALUES
                    (:event_id,:title,:description,:category,:date,:link,:source,:embedding)
                ON CONFLICT(event_id) DO UPDATE SET
                    title       = excluded.title,
                    description = excluded.description,
                    category    = excluded.category,
                    date        = excluded.date,
                    link        = excluded.link,
                    source      = excluded.source,
                    embedding   = excluded.embedding
            """, {
                "event_id":    e["event_id"],
                "title":       e["title"],
                "description": e.get("description",""),
                "category":    e.get("category",""),
                "date":        e.get("date",""),
                "link":        e.get("link",""),
                "source":      e.get("source","manual"),
                "embedding":   blob,
            })
            saved += 1
    logger.info("Saved/updated %d events.", saved)
    return saved


def get_all_events() -> list[dict]:
    with get_db() as (_, cursor):
        cursor.execute(
            "SELECT event_id,title,description,category,date,link,source FROM events"
        )
        return [dict(row) for row in cursor.fetchall()]


# ── Scrape metadata ───────────────────────────────────────────────────────────

def save_scrape_meta(status: str, event_count: int, message: str = "") -> None:
    """Persist last-scrape info so the UI can show 'Last synced 5 min ago'."""
    with get_db() as (_, cursor):
        cursor.execute("""
            INSERT INTO scrape_meta (scraped_at, status, event_count, message)
            VALUES (?, ?, ?, ?)
        """, (datetime.now().isoformat(), status, event_count, message))


def get_last_scrape_meta() -> dict | None:
    with get_db() as (_, cursor):
        cursor.execute(
            "SELECT * FROM scrape_meta ORDER BY scraped_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None
