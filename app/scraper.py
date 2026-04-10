"""
scraper.py
----------
Scrapes live events from https://eventhubcc.vit.ac.in/EventHub/

Strategy (in order):
  1. requests + BeautifulSoup  — works if the page is server-side rendered
  2. If the page body is empty / JS-only → returns ScrapeResult with
     status="js_required" so the caller can surface a helpful message.

Why NOT Selenium here:
  Selenium requires a local Chrome install which is unavailable on
  Streamlit Community Cloud free tier without heavy package setup.
  The requests approach is instant, zero-dependency on browsers, and
  sufficient for most SSR/PHP sites.  If VIT ever migrates to a pure
  SPA, the status flag lets the UI degrade gracefully.

Output schema (each event dict):
  event_id    str   — stable sha1[:16] of title
  title       str
  description str
  category    str   — inferred from text (Workshop / Hackathon / etc.)
  date        str   — raw date string extracted via regex, or ""
  date_iso    str   — YYYY-MM-DD if parseable, else ""
  link        str   — absolute URL to the event page
  source      str   — always "eventhub_live"
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.config import EVENTHUB_URL, SCRAPE_TIMEOUT
from app.logger import logger

# ── Regex ────────────────────────────────────────────────────────────────────
_DATE_PATTERNS = [
    # 2025-03-15  or  15-03-2025
    re.compile(r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b"),
    # 15 March 2025   or   15-Mar-25
    re.compile(r"\b(\d{1,2}[\s\-/](?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
               r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
               r"Nov(?:ember)?|Dec(?:ember)?)[\s\-/]\d{2,4})\b", re.I),
    # March 15, 2025
    re.compile(r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
               r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
               r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})\b", re.I),
]

_MONTH_MAP = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,
    "apr":4,"april":4,"may":5,"jun":6,"june":6,"jul":7,"july":7,
    "aug":8,"august":8,"sep":9,"september":9,"oct":10,"october":10,
    "nov":11,"november":11,"dec":12,"december":12,
}

_CATEGORY_RE = re.compile(
    r"\b(workshop|seminar|talk|webinar|hackathon|conference|"
    r"sports?|cultural|concert|meetup|competition|exhibition|"
    r"fest|olympiad|bootcamp|sprint|championship)\b",
    re.I,
)

# CSS class fragments that are likely event containers
_CARD_CLASSES = ["card", "event", "listing", "item", "tile", "post"]

# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_date_iso(raw: str) -> str:
    """Try to convert a raw date string to YYYY-MM-DD.  Returns '' on failure."""
    raw = raw.strip()

    # Already ISO
    m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", raw)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"

    # dd-Mon-yyyy  or  dd Mon yyyy  or  Mon dd, yyyy
    parts = re.split(r"[\s,\-/]+", raw)
    if len(parts) >= 3:
        # try (day, month, year)
        for d_idx, m_idx, y_idx in [(0,1,2), (1,0,2)]:
            try:
                day   = int(parts[d_idx])
                month = _MONTH_MAP.get(parts[m_idx].lower()[:3])
                year  = int(parts[y_idx]) if len(parts[y_idx]) == 4 else (2000 + int(parts[y_idx]))
                if month:
                    return date(year, month, day).isoformat()
            except (ValueError, IndexError):
                pass
    return ""


def _extract_date(text: str) -> tuple[str, str]:
    """Return (raw_date_str, iso_date_str)."""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(1)
            return raw, _parse_date_iso(raw)
    return "", ""


def _extract_category(text: str) -> str:
    m = _CATEGORY_RE.search(text)
    return m.group(1).title() if m else ""


def _stable_id(title: str) -> str:
    return hashlib.sha1(title.strip().lower().encode()).hexdigest()[:16]


def _find_title(tag) -> str:
    """Find the most likely title inside a card element."""
    # Prefer heading tags
    for level in ["h1","h2","h3","h4","h5","h6"]:
        el = tag.find(level)
        if el and el.get_text(strip=True):
            return _normalize(el.get_text())
    # Fall back to .title / .event-title class
    for cls in ["title","event-title","card-title","event-name","name"]:
        el = tag.find(class_=re.compile(cls, re.I))
        if el and el.get_text(strip=True):
            return _normalize(el.get_text())
    # Last resort: first non-empty line of card text
    first_line = tag.get_text("\n", strip=True).split("\n")[0]
    return _normalize(first_line)


def _find_link(tag, base_url: str) -> str:
    a = tag.find("a", href=True)
    if not a:
        return ""
    href = a["href"].strip()
    if href.startswith("http"):
        return href
    return urljoin(base_url, href)


def _find_description(tag, title: str) -> str:
    # Look for explicit description / body elements
    for cls in ["description","desc","body","content","card-body","card-text","summary","detail"]:
        el = tag.find(class_=re.compile(cls, re.I))
        if el:
            txt = _normalize(el.get_text())
            if txt and txt.lower() != title.lower():
                return txt[:500]
    # Fall back: full text minus the title
    full = _normalize(tag.get_text(" "))
    desc = full.replace(title, "").strip(" |-:")
    return desc[:500]


# ── Dataclass for result ─────────────────────────────────────────────────────

@dataclass
class ScrapeResult:
    events:    list[dict[str, Any]] = field(default_factory=list)
    status:    str   = "ok"         # "ok" | "js_required" | "empty" | "error"
    message:   str   = ""
    scraped_at: str  = field(default_factory=lambda: datetime.now().isoformat())
    duration_s: float = 0.0


# ── Main scrape function ─────────────────────────────────────────────────────

def scrape_eventhub(url: str = EVENTHUB_URL) -> ScrapeResult:
    """
    Fetch and parse the VIT EventHub page.
    Returns a ScrapeResult with parsed events or an error status.
    """
    t0 = time.time()
    logger.info("Scraping %s …", url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
        "Cache-Control":   "no-cache",
    }

    # ── Fetch ────────────────────────────────────────────────────────────────
    try:
        resp = requests.get(url, headers=headers, timeout=SCRAPE_TIMEOUT, verify=False)
        resp.raise_for_status()
    except requests.exceptions.SSLError:
        try:
            resp = requests.get(url, headers=headers, timeout=SCRAPE_TIMEOUT, verify=False)
            resp.raise_for_status()
        except Exception as exc:
            return ScrapeResult(status="error", message=str(exc), duration_s=time.time()-t0)
    except requests.exceptions.ConnectionError as exc:
        return ScrapeResult(
            status="error",
            message=f"Cannot reach {url}. The site may be on VIT's internal network.",
            duration_s=time.time()-t0,
        )
    except Exception as exc:
        return ScrapeResult(status="error", message=str(exc), duration_s=time.time()-t0)

    # ── Parse ────────────────────────────────────────────────────────────────
    soup = BeautifulSoup(resp.text, "lxml")

    # Detect JS-only shells (React/Angular/Vue)
    body_text = _normalize(soup.body.get_text() if soup.body else "")
    if len(body_text) < 200 and soup.find("div", id=re.compile(r"^(root|app)$", re.I)):
        return ScrapeResult(
            status="js_required",
            message=(
                "EventHub appears to be a JavaScript SPA. "
                "The page needs a browser to render. "
                "Please install the Selenium + Chromium packages (see README) "
                "or contact VIT IT to request a static/API endpoint."
            ),
            duration_s=time.time()-t0,
        )

    # ── Find event cards ─────────────────────────────────────────────────────
    cards = []

    # Strategy 1: find divs whose class contains a card-like word
    for cls in _CARD_CLASSES:
        found = soup.find_all("div", class_=re.compile(cls, re.I))
        if found:
            cards.extend(found)
            break

    # Strategy 2: look for <article> tags
    if not cards:
        cards = soup.find_all("article")

    # Strategy 3: any <li> with an <a> and at least one heading
    if not cards:
        cards = [
            li for li in soup.find_all("li")
            if li.find(re.compile("h[1-6]")) and li.find("a")
        ]

    # Strategy 4: grab all <a> tags that look like event links and build synthetic cards
    if not cards:
        cards = [
            a.parent for a in soup.find_all("a", href=True)
            if any(kw in (a.get("href","") + a.get_text()).lower()
                   for kw in ["event","register","details","workshop","hackathon"])
        ]

    if not cards:
        return ScrapeResult(
            status="empty",
            message="Page loaded but no event cards were found. The HTML structure may have changed.",
            duration_s=time.time()-t0,
        )

    # ── Extract events ───────────────────────────────────────────────────────
    events: list[dict] = []
    seen: set[str] = set()

    for card in cards:
        title = _find_title(card)
        if not title or len(title) < 4:
            continue

        # Deduplicate by normalised title
        key = title.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        raw_text  = _normalize(card.get_text(" "))
        raw_date, iso_date = _extract_date(raw_text)
        category  = _extract_category(raw_text)
        link      = _find_link(card, url)
        desc      = _find_description(card, title)

        events.append({
            "event_id":    _stable_id(title),
            "title":       title,
            "description": desc,
            "category":    category,
            "date":        iso_date or raw_date,      # prefer ISO
            "date_raw":    raw_date,
            "link":        link,
            "source":      "eventhub_live",
        })

    duration = time.time() - t0
    logger.info("Scraped %d events in %.1fs", len(events), duration)

    if not events:
        return ScrapeResult(
            status="empty",
            message="Cards were found but no titles could be extracted.",
            duration_s=duration,
        )

    return ScrapeResult(events=events, status="ok", duration_s=duration)
