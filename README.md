# 🎓 VIT Event Recommender

AI-powered personalised event recommendations for VIT students.
Semantic similarity via `all-MiniLM-L6-v2` + FAISS vector search.

---

## 🚀 Deploy to Streamlit Community Cloud (free, public URL)

1. **Fork / push this repo** to your GitHub account
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, branch `main`, entry file `streamlit_app.py`
4. In **Advanced settings → Secrets**, paste:
   ```toml
   SENDER_EMAIL    = "your_gmail@gmail.com"
   SENDER_PASSWORD = "your_16_char_app_password"
   ```
5. Click **Deploy** — your public URL is live in ~2 minutes

> **Email is optional.** The recommender works without email credentials;
> you'll just see a warning in the Admin tab.

---

## 🖥️ Run Locally

```bash
# 1. Clone
git clone https://github.com/yourusername/vit-event-recommender.git
cd vit-event-recommender

# 2. Create venv
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Configure email (optional)
cp .env.example .env
# Edit .env with your Gmail + App Password

# 5. Launch
streamlit run streamlit_app.py
```

---

## 📁 Project Structure

```
vit-event-recommender/
├── streamlit_app.py          ← Streamlit UI (entry point)
├── pipeline.py               ← Headless CLI runner
├── scheduler.py              ← Daily APScheduler job
├── requirements.txt
├── .env.example
├── .streamlit/
│   └── config.toml           ← Theme + server settings
├── data/
│   └── events.json           ← 20 sample VIT events
└── app/
    ├── config.py             ← Paths, constants, env vars
    ├── database.py           ← SQLite + context-manager get_db()
    ├── embedder.py           ← Lazy SentenceTransformer wrapper
    ├── vector_store.py       ← FAISS index (lazy singleton)
    ├── recommender.py        ← Similarity + feedback re-ranking
    ├── email_service.py      ← SMTP HTML email sender
    ├── user_service.py       ← User CRUD
    ├── event_storage.py      ← Event upsert + retrieval
    ├── feedback.py           ← Rating storage
    └── ingestion/
        ├── json_source.py    ← Load from JSON
        └── csv_source.py     ← Load from CSV
```

---

## 🔧 Key Architecture Improvements (vs original)

| # | Problem | Fix |
|---|---------|-----|
| 1 | N+1 DB queries in recommender | Batch `WHERE event_id IN (…)` — 1 query total |
| 2 | N+1 DB queries in email service | Same batched fetch |
| 3 | DB connections leaked on exception | `@contextmanager get_db()` — always commits/closes |
| 4 | `INSERT OR IGNORE` dropped re-imports | `ON CONFLICT DO UPDATE` upsert |
| 5 | Model loaded at import time | Lazy loading — only on first recommendation call |
| 6 | Module-level `VectorStore()` instantiation | `get_vector_store()` lazy singleton |
| 7 | `input()` at module level in register_user.py | Removed — handled by Streamlit sidebar |
| 8 | `feedback.py` was empty | Fully implemented with upsert |
| 9 | `csv_source.py` was empty | Fully implemented with pandas |
| 10 | Hard-coded string paths broke on Windows | `pathlib.Path` throughout |

---

## 📧 Gmail App Password Setup

1. Go to your Google Account → Security → 2-Step Verification (enable it)
2. Search "App passwords" → Create one for "Mail"
3. Use the 16-character password as `SENDER_PASSWORD`

---

## Author
Virat Dwivedi · VIT Event Recommender · MIT License
