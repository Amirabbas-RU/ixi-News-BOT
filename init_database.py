
import sqlite3
import os
from config import DB_NAME, RESET_DATABASE, DB_PATH

#----------------------<< define tables functions >>----------------------
def init_db():
    if RESET_DATABASE:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            print("Database reset: deleted old database.")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

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
