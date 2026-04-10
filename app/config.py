import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR          = Path(__file__).resolve().parent.parent
DATA_DIR          = BASE_DIR / "data"
DATABASE_PATH     = str(BASE_DIR / "events.db")
FAISS_INDEX_FILE  = str(BASE_DIR / "faiss.index")

# ── Scraper ─────────────────────────────────────────────────────────────────
EVENTHUB_URL      = "https://eventhubcc.vit.ac.in/EventHub/"
SCRAPE_TIMEOUT    = 20          # seconds per HTTP request
SCRAPE_CACHE_TTL  = 3600        # re-scrape if data is older than 1 hour

# ── ML / Vector ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL   = "all-MiniLM-L6-v2"
EMBEDDING_DIM     = 384
TOP_K             = 5

# ── Email ────────────────────────────────────────────────────────────────────
SENDER_EMAIL      = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD   = os.getenv("SENDER_PASSWORD")
SMTP_HOST         = "smtp.gmail.com"
SMTP_PORT         = 587
