"""
database.py  —  SQLite context-manager wrapper + schema + migrations
"""
import sqlite3
from contextlib import contextmanager
from app.config import DATABASE_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables() -> None:
    with get_db() as (conn, cursor):

        # ── Create tables if they don't exist ────────────────────────────
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                category    TEXT DEFAULT '',
                date        TEXT DEFAULT '',
                link        TEXT DEFAULT '',
                source      TEXT DEFAULT 'manual',
                embedding   BLOB
            );

            CREATE TABLE IF NOT EXISTS users (
                user_email  TEXT PRIMARY KEY,
                interests   TEXT,
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback (
                user_email  TEXT NOT NULL,
                event_id    TEXT NOT NULL,
                rating      INTEGER CHECK(rating BETWEEN 1 AND 5),
                PRIMARY KEY (user_email, event_id)
            );

            CREATE TABLE IF NOT EXISTS scrape_meta (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scraped_at  TEXT NOT NULL,
                status      TEXT NOT NULL,
                event_count INTEGER DEFAULT 0,
                message     TEXT DEFAULT ''
            );
        """)

        # ── Safe migrations: add columns added after initial deploy ──────
        # This handles users who have an old DB without the new columns.
        existing_events = {
            row[1] for row in cursor.execute("PRAGMA table_info(events)")
        }
        if "source" not in existing_events:
            cursor.execute(
                "ALTER TABLE events ADD COLUMN source TEXT DEFAULT 'manual'"
            )

        conn.commit()
