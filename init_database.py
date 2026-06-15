
import os
import re
import sqlite3
from config import DB_NAME, DB_PATH, RESET_DATABASE
import set_path

ENV_PATH = os.path.join(set_path.base_path, "main.env")


def _set_reset_false():
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            text = f.read()
        text = re.sub(
            r"^(RESET_DATABASE\s*=\s*)true",
            r"\1false",
            text,
            count=1,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print("[Database] RESET_DATABASE set to false in main.env")
    except Exception as e:
        print(f"[Database] Failed to update RESET_DATABASE: {e}")


#----------------------<< define tables functions >>----------------------
def init_db():
    if RESET_DATABASE and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[Database] Deleted existing database: {DB_PATH}")
        _set_reset_false()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forex_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        country TEXT,
        event_date TEXT,
        event_time TEXT,
        impact TEXT,
        forecast TEXT,
        previous TEXT,
        url TEXT UNIQUE,
        alert_pre_sent INTEGER DEFAULT 0,
        alert_15min_sent INTEGER DEFAULT 0,
        alert_30min_sent INTEGER DEFAULT 0,
        result_sent INTEGER DEFAULT 0,
        news_inserted INTEGER DEFAULT 0,
        analysis TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    try:
        cursor.execute("ALTER TABLE forex_events RENAME COLUMN alert_5min_sent TO alert_pre_sent")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE forex_events ADD COLUMN alert_pre_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    for col, typ in [("analysis", "TEXT"), ("news_inserted", "INTEGER DEFAULT 0")]:
        try:
            cursor.execute(f"ALTER TABLE forex_events ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        url TEXT UNIQUE,
        image_url TEXT,
        source TEXT,
        published_at TEXT,
        content TEXT,
        importance_score REAL,
        summary TEXT,
        summarized INTEGER DEFAULT 0,
        published INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


#----------------------<< initialize db tables >>----------------------
init_db()
