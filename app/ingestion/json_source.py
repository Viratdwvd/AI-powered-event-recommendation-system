"""
json_source.py
--------------
Load events from a JSON file.  Each item is normalised to the standard
event dict schema and assigned a stable event_id derived from the title
(so re-importing the same file doesn't generate duplicate rows).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.logger import logger


def load_events_from_json(file_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(file_path) if file_path else DATA_DIR / "events.json"

    if not path.exists():
        logger.warning("JSON source not found: %s", path)
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = []
    for item in data:
        title = item.get("title", "").strip()
        if not title:
            continue

        # Stable ID: sha1 of the title (first 16 hex chars)
        event_id = hashlib.sha1(title.encode()).hexdigest()[:16]

        events.append(
            {
                "event_id": event_id,
                "title": title,
                "description": item.get("description", ""),
                "category": item.get("category", ""),
                "date": item.get("date", ""),
                "link": item.get("link", ""),
            }
        )

    logger.info("Loaded %d events from %s.", len(events), path)
    return events
