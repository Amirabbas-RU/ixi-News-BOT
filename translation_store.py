"""Persistent Farsi translation store.

Separate SQLite DB that caches English -> Persian translations so the bot
doesn't have to call OpenRouter for the same title/string every cycle.
Persists across restarts (the in-memory title_cache in openrouter_summarizer
does not).

DB file lives next to the main DB (news_storage.db) via set_path.base_path.
"""
import os
import sqlite3
import threading

import set_path

TRANSLATIONS_DB = os.path.join(set_path.base_path, "translations.db")

_lock = threading.Lock()
_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(TRANSLATIONS_DB, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS translations (
                en TEXT PRIMARY KEY,
                fa TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        _conn.commit()
    return _conn


def get_translation(en: str) -> str | None:
    """Return cached Farsi translation for `en`, or None if not cached."""
    if not en:
        return None
    try:
        cur = _get_conn().cursor()
        cur.execute("SELECT fa FROM translations WHERE en = ?", (en,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def save_translation(en: str, fa: str):
    """Persist en -> fa. Fails silently (never blocks a send)."""
    if not en or not fa:
        return
    try:
        with _lock:
            conn = _get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO translations (en, fa, created_at) "
                "VALUES (?, ?, datetime('now'))",
                (en, fa),
            )
            conn.commit()
    except Exception:
        try:
            _get_conn().rollback()
        except Exception:
            pass