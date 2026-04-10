"""
csv_source.py
-------------
Load events from a CSV file.
Was an empty stub in the original codebase.

Expected columns (case-insensitive):
    title, description, category, date, link
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from app.logger import logger


def load_events_from_csv(file_path: str | Path) -> list[dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        logger.warning("CSV source not found: %s", path)
        return []

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    required = {"title"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    events = []
    for _, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        if not title:
            continue

        event_id = hashlib.sha1(title.encode()).hexdigest()[:16]

        events.append(
            {
                "event_id": event_id,
                "title": title,
                "description": str(row.get("description", "")),
                "category": str(row.get("category", "")),
                "date": str(row.get("date", "")),
                "link": str(row.get("link", "")),
            }
        )

    logger.info("Loaded %d events from %s.", len(events), path)
    return events
