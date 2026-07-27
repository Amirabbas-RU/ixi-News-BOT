import set_path
import config
import init_database
import os
import time
import telebot
import sqlite3
from logger import logger, green
import re
import sys
import json
import threading
import atexit

from sources_cnbc import CNBCRSS
from sources_yahoo import YahooRSS

from openrouter_summarizer import summarize_news_fa, summarize_forex_event_fa, translate_title_fa
from sources_forexfactory import ForexFactoryCalendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ---------------------------------<< in order to avoid freeze .exe file >>---------------------------------
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

# ---------------------------------<< define global variables and load data >>---------------------------------
NEWS_UPDATE_INTERVAL_MINUTES = config.NEWS_UPDATE_INTERVAL_MINUTES

DB_NAME = config.DB_NAME
DB_PATH = config.DB_PATH

OPENROUTER_API_KEY = config.OPENROUTER_API_KEY
OPENROUTER_MODEL = config.OPENROUTER_MODEL
OPENROUTER_BASE_URL = config.OPENROUTER_BASE_URL

TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL_ID = config.TELEGRAM_CHANNEL_ID

MIN_IMPACT_SCORE = config.MIN_IMPACT_SCORE
FOREX_MIN_SCORE = config.FOREX_MIN_SCORE

HIGH_IMPACT_KEYWORDS = config.HIGH_IMPACT_KEYWORDS
SOURCE_SCORE = config.SOURCE_SCORE

FOREXFACTORY_CALENDAR_URL = config.FOREXFACTORY_CALENDAR_URL
CALENDAR_TZ = ZoneInfo(config.CALENDAR_TIMEZONE)
FOREX_ALERT_IMPACTS = [x.strip() for x in config.FOREX_ALERT_IMPACTS.split(",")]
FOREX_IMPACT_EMOJIS = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
FOREX_IMPACT_LABELS = {"High": "تاثیر خبر بالا", "Medium": "تاثیر خبر متوسط", "Low": "تاثیر خبر پایین"}

TIME_PROTECTION = config.TIME_PROTECTION
NEWS_AGE_LIMIT_HOURS = config.NEWS_AGE_LIMIT_HOURS
MAX_NEWS_AGE_HOURS = 48
FOREX_IMAGE_SEND = config.FOREX_IMAGE_SEND
FOREX_IMAGE_SEND_TIME = config.FOREX_IMAGE_SEND_TIME
FORCE_SNAPSHOT = config.FORCE_SNAPSHOT
_last_shown_date = None
db_conn = None


def reload_config():
    config.reload_env()
    global NEWS_UPDATE_INTERVAL_MINUTES, DB_NAME, DB_PATH
    global OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
    global MIN_IMPACT_SCORE, FOREX_MIN_SCORE
    global HIGH_IMPACT_KEYWORDS, SOURCE_SCORE
    global FOREXFACTORY_CALENDAR_URL, CALENDAR_TZ, FOREX_ALERT_IMPACTS
    global TIME_PROTECTION, NEWS_AGE_LIMIT_HOURS
    global FOREX_IMAGE_SEND, FOREX_IMAGE_SEND_TIME, FORCE_SNAPSHOT

    NEWS_UPDATE_INTERVAL_MINUTES = config.NEWS_UPDATE_INTERVAL_MINUTES
    DB_NAME = config.DB_NAME
    DB_PATH = config.DB_PATH
    OPENROUTER_API_KEY = config.OPENROUTER_API_KEY
    OPENROUTER_MODEL = config.OPENROUTER_MODEL
    OPENROUTER_BASE_URL = config.OPENROUTER_BASE_URL
    TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHANNEL_ID = config.TELEGRAM_CHANNEL_ID
    MIN_IMPACT_SCORE = config.MIN_IMPACT_SCORE
    FOREX_MIN_SCORE = config.FOREX_MIN_SCORE
    HIGH_IMPACT_KEYWORDS = config.HIGH_IMPACT_KEYWORDS
    SOURCE_SCORE = config.SOURCE_SCORE
    FOREXFACTORY_CALENDAR_URL = config.FOREXFACTORY_CALENDAR_URL
    CALENDAR_TZ = ZoneInfo(config.CALENDAR_TIMEZONE)
    FOREX_ALERT_IMPACTS = [x.strip() for x in config.FOREX_ALERT_IMPACTS.split(",")]
    TIME_PROTECTION = config.TIME_PROTECTION
    NEWS_AGE_LIMIT_HOURS = config.NEWS_AGE_LIMIT_HOURS
    FOREX_IMAGE_SEND = config.FOREX_IMAGE_SEND
    FOREX_IMAGE_SEND_TIME = config.FOREX_IMAGE_SEND_TIME
    FORCE_SNAPSHOT = config.FORCE_SNAPSHOT


# ---------------------------------<< setup telegram bot >>---------------------------------
my_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
bot_username = my_bot.get_me().username


# ---------------------------------<< program main body >>---------------------------------
def insert_news(news: dict) -> bool:
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT 1 FROM news WHERE url = ? LIMIT 1", (news["url"],))
        if cursor.fetchone():
            return False

        cursor.execute(
            """
        INSERT INTO news (title, url, image_url, source, published_at, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                news["title"],
                news["url"],
                news["image_url"],
                news["source"],
                news["published_at"],
                news["content"],
            ),
        )
        db_conn.commit()
        return True
    except Exception as e:
        db_conn.rollback()
        logger.warning(f"Insert failed: {e}")
        return False


def update_news_summary(news_id: int, summary: str):
    try:
        db_conn.execute("UPDATE news SET summary = ? WHERE id = ?", (summary, news_id))
        db_conn.commit()
    except sqlite3.Error as e:
        db_conn.rollback()
        logger.error(f"Database error in update_news_summary: {e}")


def get_unsent_high_score_news(threshold: float = 7.0, source: str = None, max_age_hours: int = None):
    try:
        cursor = db_conn.cursor()
        query = """
            SELECT id, title, content, source, importance_score, image_url, url
            FROM news
            WHERE importance_score >= ?
                AND published = 0
        """
        params = [threshold]
        if TIME_PROTECTION:
            limit = max_age_hours if max_age_hours is not None else NEWS_AGE_LIMIT_HOURS
            query += " AND created_at >= datetime('now', '-' || ? || ' hours')"
            params.append(limit)
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY importance_score DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        logger.error(f"DB error in get_unsent_high_score_news: {e}")
        return []

    news_list = []
    for row in rows:
        news_list.append(
            {
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "source": row[3],
                "importance_score": row[4],
                "image_url": row[5],
                "url": row[6],
            }
        )
    return news_list


def mark_news_as_summarized(news_id):
    try:
        db_conn.execute("UPDATE news SET summarized = 1 WHERE id = ?", (news_id,))
        db_conn.commit()
    except sqlite3.OperationalError as e:
        db_conn.rollback()
        logger.error(f"DB error in mark_news_as_summarized: {e}")


def get_today_sent_count() -> int:
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM news WHERE published = 1 AND sent_at LIKE ?",
            (f"{today}%",),
        )
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error counting today's sent news: {e}")
        return 0


def mark_news_as_sent(news_id):
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            "UPDATE news SET published = 1, sent_at = ? WHERE id = ?",
            (now_str, news_id),
        )
        db_conn.commit()
    except sqlite3.OperationalError as e:
        db_conn.rollback()
        logger.error(f"DB error in mark_news_as_sent: {e}")


# ---------------------------------<< news scoring section >>---------------------------------
def calculate_keyword_score(text: str) -> int:
    score = 0
    text_lower = text.lower()
    for keyword, value in HIGH_IMPACT_KEYWORDS.items():
        if keyword.lower() in text_lower:
            score += value
    return score


def calculate_total_score(news_item: dict) -> float:
    score = calculate_keyword_score(news_item["title"])
    score += calculate_keyword_score(news_item.get("content", ""))
    score += SOURCE_SCORE.get(news_item["source"], 0)
    return score


def escape_markdown_v2(text: str) -> str:
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)


def send_with_retry(
    bot, chat_id, content, image_url=None, max_retries=3, reply_to_message_id=None
):
    retry_delays = [2, 5, 10]

    for attempt in range(max_retries):
        try:
            if image_url:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=content,
                    parse_mode="MarkdownV2",
                    reply_to_message_id=reply_to_message_id,
                )
            else:
                bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    parse_mode="MarkdownV2",
                    reply_to_message_id=reply_to_message_id,
                )

            logger.info(green(f"Message sent successfully (attempt {attempt + 1})"))
            return True

        except Exception as e:
            logger.warning(f"Send attempt {attempt + 1} failed: {e}")

            if attempt < max_retries - 1:
                delay = retry_delays[attempt] if attempt < len(retry_delays) else 10
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"Failed to send after {max_retries} attempts")

    return False


# ---------------------------------<< Forex Calendar Functions >>---------------------------------
def insert_forex_event(event: dict) -> bool:
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT 1 FROM forex_events WHERE url = ? LIMIT 1", (event["url"],)
        )
        if cursor.fetchone():
            return False
        cursor.execute(
            """
            INSERT INTO forex_events (title, country, event_date, event_time, impact, forecast, previous, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event["title"],
                event["country"],
                event["date"],
                event["time"],
                event["impact"],
                event["forecast"],
                event["previous"],
                event["url"],
            ),
        )
        db_conn.commit()
        return True
    except Exception as e:
        db_conn.rollback()
        logger.warning(f"Insert forex event failed: {e}")
        return False


def get_pending_forex_alerts() -> list[dict]:
    try:
        today_str = datetime.now().astimezone().strftime("%m-%d-%Y")
        cursor = db_conn.cursor()
        cursor.execute(
            """
            SELECT id, title, country, event_date, event_time, impact,
                   forecast, previous, url, analysis,
                   alert_pre_sent, alert_15min_sent, alert_30min_sent, result_sent, news_inserted
            FROM forex_events
            WHERE news_inserted = 0 OR event_date = ?
            ORDER BY event_date, event_time
        """,
            (today_str,),
        )
        cols = [
            "id",
            "title",
            "country",
            "event_date",
            "event_time",
            "impact",
            "forecast",
            "previous",
            "url",
            "analysis",
            "alert_pre_sent",
            "alert_15min_sent",
            "alert_30min_sent",
            "result_sent",
            "news_inserted",
        ]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get pending forex alerts error: {e}")
        return []


def mark_forex_alert(alert_type: str, event_id: int):
    col_map = {
        "pre": "alert_pre_sent",
        "15min": "alert_15min_sent",
        "30min": "alert_30min_sent",
        "result": "result_sent",
        "news": "news_inserted",
    }
    col = col_map.get(alert_type)
    if not col:
        return
    try:
        db_conn.execute(f"UPDATE forex_events SET {col} = 1 WHERE id = ?", (event_id,))
        db_conn.commit()
    except Exception as e:
        db_conn.rollback()
        logger.error(f"Mark forex alert error: {e}")


def update_forex_analysis(event_id: int, analysis: str):
    try:
        db_conn.execute(
            "UPDATE forex_events SET analysis = ? WHERE id = ?",
            (analysis, event_id),
        )
        db_conn.commit()
    except Exception as e:
        db_conn.rollback()
        logger.error(f"Update forex analysis error: {e}")


def parse_forex_datetime(date_str: str, time_str: str) -> datetime | None:
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
        return naive.replace(tzinfo=CALENDAR_TZ)
    except Exception as e:
        logger.warning(f"Parse forex datetime failed: {date_str} {time_str} - {e}")
        return None


def send_forex_message(text: str) -> int | None:
    for attempt in range(3):
        try:
            msg = my_bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID, text=text, parse_mode="MarkdownV2"
            )
            logger.info(green("Forex alert sent successfully"))
            return msg.message_id
        except Exception as e:
            logger.warning(f"Forex send attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return None


def mark_past_forex_events_done():
    try:
        now_dt = datetime.now().astimezone()
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT id, event_date, event_time FROM forex_events WHERE news_inserted = 0"
        )
        for row in cursor.fetchall():
            ev_id, ev_date, ev_time = row
            ev_dt = parse_forex_datetime(ev_date, ev_time)
            if ev_dt and (ev_dt - now_dt).total_seconds() / 60.0 < -60:
                db_conn.execute(
                    "UPDATE forex_events SET news_inserted = 1 WHERE id = ?",
                    (ev_id,),
                )
        db_conn.commit()
    except Exception as e:
        db_conn.rollback()
        logger.error(f"Mark past events error: {e}")


def insert_forex_into_news(ev: dict):
    try:
        title = ev["title"]
        url = ev.get(
            "url", f"https://www.forexfactory.com/calendar?day={ev['event_date']}"
        )
        content_parts = []
        if ev.get("forecast"):
            content_parts.append(f"Forecast: {ev['forecast']}")
        if ev.get("previous"):
            content_parts.append(f"Previous: {ev['previous']}")
        content_parts.append(f"Impact: {ev['impact']}")
        content_parts.append(f"Country: {ev['country']}")
        content = " | ".join(content_parts)

        news_item = {"title": title, "content": content, "source": "ForexFactory"}
        s = calculate_total_score(news_item)
        passes_forex = ev["impact"] in FOREX_ALERT_IMPACTS and s >= FOREX_MIN_SCORE
        importance_score = max(s, FOREX_MIN_SCORE) if passes_forex else s

        cursor = db_conn.cursor()
        cursor.execute("SELECT 1 FROM news WHERE url = ?", (url,))
        if cursor.fetchone():
            return
        cursor.execute(
            """
            INSERT INTO news (title, url, image_url, source, published_at, content, importance_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                title,
                url,
                None,
                "ForexFactory",
                f"{ev['event_date']} {ev['event_time']}",
                content,
                importance_score,
            ),
        )
        db_conn.commit()
    except Exception as e:
        db_conn.rollback()
        logger.error(f"Insert forex into news error: {e}")


def forex_event_to_news_item(ev: dict) -> dict:
    content_parts = []
    if ev.get("forecast"):
        content_parts.append(f"📊 Forecast: {ev['forecast']}")
    if ev.get("previous"):
        content_parts.append(f"📉 Previous: {ev['previous']}")
    if ev.get("country"):
        content_parts.append(f"🌍 Country: {ev['country']}")
    content_parts.append(f"⚡ Impact: {ev['impact']}")

    return {
        "title": ev["title"],
        "url": ev["url"],
        "image_url": None,
        "source": "ForexFactory",
        "published_at": f"{ev['event_date']} {ev['event_time']}",
        "content": " | ".join(content_parts) if content_parts else ev["title"],
    }


def _print_forex_table(pending: list[dict], now_dt: datetime):
    lines = []
    sep = "─" * 106
    lines.append(f"── ForexFactory Pending Events ({len(pending)}) {'─' * 52}")
    header = f"{'S':<3} {'Impact':<10} {'Country':<10} {'Title':<50} {'Date':<15} {'Time':<10} {'In':<8}"
    lines.append(header)
    lines.append("─" * 106)
    for ev in pending:
        ev_dt = parse_forex_datetime(ev["event_date"], ev["event_time"])
        if ev_dt is None:
            continue
        mins = (ev_dt - now_dt).total_seconds() / 60.0
        in_str = f"{mins:+.0f}m" if abs(mins) < 10000 else f"{mins / 60:+.0f}h"
        title = ev["title"][:48]
        status = "✅" if ev.get("alert_pre_sent") else "·"
        lines.append(
            f"{status:<3} {ev['impact']:<10} {ev['country']:<10} {title:<50} "
            f"{ev['event_date']:<15} {ev['event_time']:<10} {in_str:<8}"
        )
    lines.append("─" * 106)
    for line in lines:
        logger.info(line)


def check_forex_calendar():
    global _last_shown_date
    if not FOREXFACTORY_CALENDAR_URL:
        return

    logger.info("Fetching ForexFactory calendar...")
    calendar = ForexFactoryCalendar()
    events = calendar.fetch()
    new_count = 0
    for event in events:
        if insert_forex_event(event):
            new_count += 1
    if new_count:
        logger.info(green(f"{new_count} new forex events stored"))

    mark_past_forex_events_done()

    pending = get_pending_forex_alerts()
    now_dt = datetime.now().astimezone()
    logger.info(f"ForexFactory: {len(pending)} pending events to check")

    today_str = now_dt.strftime("%Y-%m-%d")
    if today_str != _last_shown_date and pending:
        _print_forex_table(pending, now_dt)
        _last_shown_date = today_str

    for ev in pending:
        ev_dt = parse_forex_datetime(ev["event_date"], ev["event_time"])
        if ev_dt is None:
            logger.warning(
                f"Forex event '{ev['title']}' on {ev['event_date']} — could not parse time, skipping"
            )
            continue

        minutes_until = (ev_dt - now_dt).total_seconds() / 60.0

        if ev["impact"] not in FOREX_ALERT_IMPACTS:
            logger.info(
                f"    → Impact '{ev['impact']}' not in alert list, marking as done"
            )
            mark_forex_alert("news", ev["id"])
            continue

        impact_emoji = FOREX_IMPACT_EMOJIS.get(ev["impact"], "⚪")
        impact_label = FOREX_IMPACT_LABELS.get(ev["impact"], "")
        alert_window = {"High": 15, "Medium": 10, "Low": 5}.get(ev["impact"], 5)

        if 0 <= minutes_until <= alert_window and not ev["alert_pre_sent"]:
            mins = round(minutes_until)
            logger.info(green(f"    → Sending pre-alert ({mins} min before release)"))
            title_fa = translate_title_fa(ev["title"]) or ""
            # save translation for daily snapshot image
            if title_fa and not ev.get("title_fa"):
                try:
                    db_conn.execute(
                        "UPDATE forex_events SET title_fa = ? WHERE id = ?",
                        (title_fa, ev["id"]),
                    )
                    db_conn.commit()
                except Exception:
                    db_conn.rollback()
            title_line = f"📌 {title_fa} ({ev['title']})" if title_fa else f"📌 {ev['title']}"
            forecast = f"📊 پیش‌بینی: {escape_markdown_v2(ev['forecast'])}" if ev.get("forecast") else ""
            previous = f"📉 قبلی: {escape_markdown_v2(ev['previous'])}" if ev.get("previous") else ""
            extra = f"\n{forecast}\n{previous}" if (forecast or previous) else ""
            text = (
                f"🔔 هشدار {mins} دقیقه قبل از انتشار خبر\n"
                f"\n"
                f"🚦 {escape_markdown_v2(ev['country'])} {impact_emoji} {impact_label}\n"
                f"\n"
                f"🗓 {escape_markdown_v2(title_line)}{extra}"
                f"\n\n💠💠 ||@ForexEyvazi|| 💠💠"
            )
            msg_id = send_forex_message(text)
            if msg_id is not None:
                try:
                    db_conn.execute(
                        "UPDATE forex_events SET alert_message_id = ? WHERE id = ?",
                        (msg_id, ev["id"]),
                    )
                    db_conn.commit()
                except Exception:
                    db_conn.rollback()
                mark_forex_alert("pre", ev["id"])
                logger.info(green(f"    ✓ Pre-alert sent for '{ev['title']}'"))
            else:
                logger.error(f"    ✗ Failed to send pre-alert for '{ev['title']}'")
        elif 0 <= minutes_until <= alert_window and ev["alert_pre_sent"]:
            logger.info(f"    → Pre-alert already sent, skipping")

        if minutes_until <= 0 and not ev["news_inserted"]:
            logger.info(f"    → Event released, inserting into news table")
            mark_forex_alert("news", ev["id"])
            insert_forex_into_news(ev)

    logger.info(green("ForexFactory alert check complete"))


# ---------------------------------<< Daily Snapshot Image >>---------------------------------

_SNAPSHOT_PROGRESS_PATH = os.path.join(os.path.dirname(__file__), ".snapshot_progress.json")


def _snapshot_progress() -> dict:
    """Load the JSON-based snapshot page tracker.  Returns {date_str: {page, total_pages, done}}."""
    try:
        with open(_SNAPSHOT_PROGRESS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_snapshot_progress(prog: dict):
    with open(_SNAPSHOT_PROGRESS_PATH, "w") as f:
        json.dump(prog, f, indent=2)


def _page_events_all_passed(page_rows: list) -> bool:
    """Return True if every event on *page_rows* has already happened (event_time in past)."""
    now = datetime.now(timezone.utc)
    for row in page_rows:
        # row is a datetime object (not a dict) — loaded from JSON snapshot
        if row is not None and row > now:
            return False
    return True


def _snapshot_already_sent_today() -> bool:
    """Check if a daily snapshot has already been sent today (UTC date)."""
    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT 1 FROM daily_snapshots WHERE snapshot_date = ?", (today_str,)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Snapshot sent-today check error: {e}")
        return False


def _record_snapshot_sent(image_path: str):
    """Record that a daily snapshot was sent today."""
    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            "INSERT OR IGNORE INTO daily_snapshots (snapshot_date, image_path, sent_at) "
            "VALUES (?, ?, ?)",
            (today_str, image_path, now_str),
        )
        db_conn.commit()
        logger.info(green(f"Daily snapshot recorded for {today_str}"))
    except Exception as e:
        db_conn.rollback()
        logger.error(f"Failed to record snapshot sent: {e}")


def check_and_send_daily_snapshot():
    """Generate and send the daily forex events snapshot image — one page per cycle.

    - Page 1 is sent at the configured time (15:05 Tehran).
    - Subsequent pages are sent only when ALL events on the previous page have passed.
    - When the last page is sent, the day is marked complete.
    """
    if not FOREX_IMAGE_SEND:
        return

    # parse target time (UTC)
    try:
        target_h, target_m = map(int, FOREX_IMAGE_SEND_TIME.strip().split(":"))
    except (ValueError, AttributeError):
        logger.error(f"Invalid FOREX_IMAGE_SEND_TIME format: {FOREX_IMAGE_SEND_TIME}")
        return

    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(ZoneInfo("Asia/Tehran"))
    target_minutes = target_h * 60 + target_m
    current_minutes = now_tehran.hour * 60 + now_tehran.minute

    logger.info(
        f"Snapshot check: enabled={FOREX_IMAGE_SEND}, "
        f"target={FOREX_IMAGE_SEND_TIME} Tehran ({target_minutes}m), "
        f"now={now_tehran.strftime('%H:%M')} Tehran ({current_minutes}m)"
    )

    # only send if we've passed the target time today
    if current_minutes < target_minutes:
        logger.info(f"Snapshot: not yet {FOREX_IMAGE_SEND_TIME} Tehran, waiting")
        return

    today_str = now_utc.strftime("%Y-%m-%d")
    prog = _snapshot_progress()
    today_prog = prog.get(today_str, {"page": 0, "total_pages": 1, "done": False})

    # Already done for today?
    if today_prog.get("done"):
        if FORCE_SNAPSHOT:
            logger.info("FORCE_SNAPSHOT=True — regenerating despite progress file")
            # reset prog so page==0 logic runs
            today_prog = {"page": 0, "total_pages": 1, "done": False}
            prog[today_str] = today_prog
        else:
            return

    from forex_image_generator import generate_forex_images

    if today_prog["page"] == 0:
        # ── First run today: generate page 1 ─────────────────────
        logger.info("Generating page 1 of daily snapshot...")

        image_paths = generate_forex_images(page_number=1)
        if not image_paths:
            logger.warning("No snapshot image generated (no events or error)")
            return

        # We need to know total pages - generate ALL to count, discard extras
        all_paths = generate_forex_images()
        total_pages = len(all_paths)
        # clean up extra generated files
        for p in all_paths:
            if p != image_paths[0] and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if total_pages == 0:
            total_pages = 1

        # Store row datetimes for pass-check (re-read from the fresh gen)
        _store_today_event_dts(now_utc)

        # Build caption and send
        caption = _build_snapshot_caption(now_utc)
        try:
            with open(image_paths[0], "rb") as img_file:
                my_bot.send_photo(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    photo=img_file,
                    caption=caption,
                )
            logger.info(green(f"Sent snapshot page 1/{total_pages}"))
        except Exception as e:
            logger.error(f"Failed to send snapshot page 1: {e}")
            return

        # Store progress (page=1 means "page 1 has been sent")
        today_prog["page"] = 1
        today_prog["total_pages"] = total_pages
        today_prog["done"] = total_pages == 1  # mark done if only 1 page
        prog[today_str] = today_prog
        _save_snapshot_progress(prog)

        if total_pages == 1:
            _record_snapshot_sent(image_paths[0])
        return

    # ── Subsequent pages: check if current page's events have all passed ──
    current_page = today_prog["page"]
    total_pages = today_prog["total_pages"]

    logger.info(f"Snapshot progress: page {current_page}/{total_pages} sent")

    if current_page >= total_pages:
        today_prog["done"] = True
        prog[today_str] = today_prog
        _save_snapshot_progress(prog)
        _record_snapshot_sent("(progressive)")
        logger.info(green("All snapshot pages sent for today"))
        return

    # Check if ALL events on current page have passed
    last_page_rows = _load_page_event_dts(now_utc, current_page - 1)  # 0-based index
    if last_page_rows is not None and not _page_events_all_passed(last_page_rows):
        logger.info(f"Page {current_page} events still pending — waiting")
        return

    # All events on previous page have passed — send next page
    next_page = current_page + 1
    logger.info(f"Sending snapshot page {next_page}/{total_pages}...")

    image_paths = generate_forex_images(page_number=next_page)
    if not image_paths:
        logger.warning(f"Page {next_page} generated no image — marking done")
        today_prog["done"] = True
        prog[today_str] = today_prog
        _save_snapshot_progress(prog)
        _record_snapshot_sent("(progressive)")
        return

    try:
        with open(image_paths[0], "rb") as img_file:
            my_bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=img_file,
                caption=_build_snapshot_caption(now_utc),
            )
        logger.info(green(f"Sent snapshot page {next_page}/{total_pages}"))
    except Exception as e:
        logger.error(f"Failed to send snapshot page {next_page}: {e}")
        return

    today_prog["page"] = next_page
    if next_page >= total_pages:
        today_prog["done"] = True
        _record_snapshot_sent("(progressive)")
        logger.info(green("All snapshot pages sent for today"))
    prog[today_str] = today_prog
    _save_snapshot_progress(prog)


def _build_snapshot_caption(now_utc: datetime) -> str:
    """Build the Persian calendar caption for snapshot images."""
    weekdays_fa = ["دوشنبه", "سه\u200cشنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
    months_en_fa = {
        1: "ژانویه", 2: "فوریه", 3: "مارس", 4: "آوریل",
        5: "مه", 6: "ژوئن", 7: "جولای", 8: "اوت",
        9: "سپتامبر", 10: "اکتبر", 11: "نوامبر", 12: "دسامبر",
    }
    tehran_dt = now_utc.astimezone(ZoneInfo("Asia/Tehran"))
    wd = weekdays_fa[tehran_dt.weekday()]
    day = tehran_dt.day
    month_en = months_en_fa[tehran_dt.month]

    # Jalali (Shamsi) date
    try:
        import jdatetime
        jdate = jdatetime.date.fromgregorian(date=tehran_dt)
        months_jalali_fa = {
            1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
            5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
            9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند",
        }
        jalali_str = f"{jdate.day} {months_jalali_fa[jdate.month]}"
    except ImportError:
        jalali_str = ""

    if jalali_str:
        return f"📅 تقویم اقتصادی {wd} {day} {month_en} | {jalali_str}\n💎💎 @ForexEyvazi 💎💎"
    else:
        return f"📅 تقویم اقتصادی {wd} {day} {month_en}\n💎💎 @ForexEyvazi 💎💎"


# ── Snapshot page event-time tracker ──────────────────────────────────
_SNAPSHOT_EVENTS_PATH = os.path.join(os.path.dirname(__file__), ".snapshot_events.json")


def _store_today_event_dts(now_utc: datetime):
    """Store the event datetimes for today's snapshot (to check pass-conditions later)."""
    from forex_image_generator import generate_forex_images, _parse_dt, _get_events, DB_PATH, CALENDAR_TIMEZONE
    from zoneinfo import ZoneInfo
    from datetime import datetime

    events = _get_events(DB_PATH, CALENDAR_TIMEZONE)
    if not events:
        return
    tz = ZoneInfo(CALENDAR_TIMEZONE)
    rows = []
    for ev in events:
        ev_dt = _parse_dt(ev["event_date"], ev["event_time"], tz)
        if ev_dt is not None:
            rows.append(ev_dt.isoformat())
    with open(_SNAPSHOT_EVENTS_PATH, "w") as f:
        json.dump(rows, f)


def _load_page_event_dts(now_utc: datetime, page_index: int) -> list | None:
    """Load the event datetimes for a specific page (0-indexed)."""
    max_rows = 20  # must match MAX_ROWS_PER_IMAGE in forex_image_generator
    try:
        with open(_SNAPSHOT_EVENTS_PATH) as f:
            all_dts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    start = page_index * max_rows
    end = start + max_rows
    page_dts = all_dts[start:end]
    if not page_dts:
        return None

    from datetime import datetime
    return [datetime.fromisoformat(d) for d in page_dts]


# ---------------------------------<< Main Function >>---------------------------------
def main():
    try:
        # reload config every cycle so changes to main.env take effect without restart
        reload_config()

        if config.ENABLE_FOREX_ALERTS:
            check_forex_calendar()
        else:
            logger.info("ForexFactory alerts disabled via config")

        # Send daily snapshot image if enabled and due
        check_and_send_daily_snapshot()

        SOURCE_CLASSES = {
            "CNBC": CNBCRSS,
            "Yahoo": YahooRSS,
        }

        sources = [
            SOURCE_CLASSES[name]()
            for name in config.ACTIVE_SOURCES
            if name in SOURCE_CLASSES
        ]

        total_new = 0

        for source in sources:
            logger.info(f"Fetching news from {source.name}")
            news_items = source.fetch()

            for news in news_items:
                pub_parsed = news.get("published_parsed")
                if pub_parsed:
                    pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                    age_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
                    if age_hours > MAX_NEWS_AGE_HOURS:
                        logger.info(
                            f"Skipping old news ({age_hours:.0f}h): {news['title']}"
                        )
                        continue
                inserted = insert_news(news)
                if inserted:
                    total_new += 1

        logger.info(f"Total new news inserted: {total_new}")

        if not sources:
            logger.info("No news RSS sources enabled")

        # ---------- Score news ----------
        try:
            cursor = db_conn.cursor()
            cursor.execute(
                "SELECT id, title, content, source FROM news WHERE importance_score IS NULL"
            )
            rows = cursor.fetchall()

            total_rows = len(rows)
            for idx, row in enumerate(rows):
                if idx % 100 == 0 and idx > 0:
                    logger.info(f"Scoring progress: {idx}/{total_rows}")
                news_id, title, content, source = row
                news_item = {"title": title, "content": content, "source": source}
                score = calculate_total_score(news_item)
                cursor.execute(
                    "UPDATE news SET importance_score = ? WHERE id = ?",
                    (score, news_id),
                )

            db_conn.commit()

        except sqlite3.Error as e:
            db_conn.rollback()
            logger.error(f"Database error: {e}")

        logger.info("Importance scores updated for new news")

        # ---------- Helper: process & send a batch of news ----------
        def _process_news_batch(news_batch: list, batch_label: str):
            if not news_batch:
                logger.info(f"No {batch_label} news to process")
                return
            sent = 0
            total = len(news_batch)
            for news in news_batch:
                news_id = news.get("id")
                title = news.get("title")
                content = news.get("content")
                image_url = news.get("image_url")

                if not content or len(content.strip()) < 30:
                    logger.warning(
                        f"{batch_label} ID {news_id} — content too short ({len(content or '')} chars), skipping"
                    )
                    mark_news_as_summarized(news_id)
                    mark_news_as_sent(news_id)
                    continue

                # ── ForexFactory: use forex-specific summarizer ──
                if batch_label == "ForexFactory":
                    forex_ev = None
                    news_url = news.get("url")
                    if news_url:
                        try:
                            cursor = db_conn.cursor()
                            cursor.execute(
                                "SELECT * FROM forex_events WHERE url = ?", (news_url,)
                            )
                            row = cursor.fetchone()
                            if row:
                                cols = [d[0] for d in cursor.description]
                                forex_ev = dict(zip(cols, row))
                        except Exception:
                            pass

                    if forex_ev:
                        summary_fa = summarize_forex_event_fa(forex_ev)
                        title_fa = forex_ev.get("title_fa") or translate_title_fa(title) or title
                    else:
                        # fallback: use generic summarizer
                        result = summarize_news_fa(title, content)
                        if not result or not result.get("title_fa"):
                            mark_news_as_summarized(news_id)
                            mark_news_as_sent(news_id)
                            continue
                        title_fa = result.get("title_fa")
                        summary_fa = result.get("summary_fa")
                else:
                    result = summarize_news_fa(title, content)

                    if not result or not result.get("title_fa"):
                        logger.warning(
                            f"{batch_label} ID {news_id} — summarization failed, marking as published"
                        )
                        mark_news_as_summarized(news_id)
                        mark_news_as_sent(news_id)
                        continue

                    title_fa = result.get("title_fa")
                    summary_fa = result.get("summary_fa")

                try:
                    update_news_summary(news_id, summary_fa)
                    mark_news_as_summarized(news_id)
                    logger.info(
                        green(f"{batch_label} ID {news_id} summarized successfully")
                    )
                except Exception as e:
                    logger.error(
                        f"Database update error for {batch_label} ID {news_id}: {e}"
                    )
                    continue

                reply_to = None
                if batch_label == "ForexFactory":
                    news_url = news.get("url")
                    if news_url:
                        try:
                            cursor = db_conn.cursor()
                            cursor.execute(
                                "SELECT alert_message_id FROM forex_events WHERE url = ?",
                                (news_url,),
                            )
                            row = cursor.fetchone()
                            if row and row[0] is not None:
                                reply_to = row[0]
                        except Exception:
                            pass

                safe_title = escape_markdown_v2(title_fa)
                safe_summary = escape_markdown_v2(summary_fa)
                diamond = "💠" if batch_label == "ForexFactory" else "💎"
                message_text = (
                    f"*{safe_title}*\n\n{safe_summary}\n\n{diamond}{diamond} ||@ForexEyvazi|| {diamond}{diamond}"
                )

                success = False
                try:
                    if image_url:
                        success = send_with_retry(
                            bot=my_bot,
                            chat_id=TELEGRAM_CHANNEL_ID,
                            content=message_text,
                            image_url=image_url,
                            max_retries=3,
                            reply_to_message_id=reply_to,
                        )
                    if not success:
                        success = send_with_retry(
                            bot=my_bot,
                            chat_id=TELEGRAM_CHANNEL_ID,
                            content=message_text,
                            image_url=None,
                            max_retries=2,
                            reply_to_message_id=reply_to,
                        )
                    if success:
                        mark_news_as_sent(news_id)
                        logger.info(
                            green(
                                f"{batch_label} ID {news_id} sent to Telegram successfully"
                            )
                        )
                        sent += 1
                    else:
                        logger.error(
                            f"Failed to send {batch_label} ID {news_id} after all retries"
                        )
                except Exception as e:
                    logger.error(
                        f"Unexpected error during sending for {batch_label} ID {news_id}: {e}"
                    )

                time.sleep(10)

            if sent == total:
                logger.info(green(f"All {sent} {batch_label} news sent to Telegram!"))
            else:
                logger.warning(
                    f"Sent {sent} out of {total} {batch_label} news. {total - sent} remaining."
                )

        # ---------- Process RSS news (threshold = MIN_IMPACT_SCORE) ----------
        rss_news = [
            n
            for n in get_unsent_high_score_news(threshold=MIN_IMPACT_SCORE)
            if n["source"] != "ForexFactory"
        ]
        if config.MAX_NEWS_PER_DAY > 0:
            sent_today = get_today_sent_count()
            remaining = max(0, config.MAX_NEWS_PER_DAY - sent_today)
            if len(rss_news) > remaining:
                logger.info(
                    f"Daily limit ({config.MAX_NEWS_PER_DAY}): {sent_today} sent today, "
                    f"sending {remaining}/{len(rss_news)} RSS items"
                )
                rss_news = rss_news[:remaining]
        _process_news_batch(rss_news, "RSS")

        # ---------- Process ForexFactory news (threshold = FOREX_MIN_SCORE) ----------
        if config.ENABLE_FOREX_ALERTS:
            forex_news = get_unsent_high_score_news(
                threshold=FOREX_MIN_SCORE, source="ForexFactory"
            )
            _process_news_batch(forex_news, "ForexFactory")

    except Exception as e:
        logger.exception(f"Error in main function: {e}")
        raise


# ---------------------------------<< optional control panel >>---------------------------------
ctrl_bot = None
if config.BOT_PANEL:
    from control_bot import register_handlers

    if config.BOT_PANEL_BOT_TOKEN:
        ctrl_bot = telebot.TeleBot(config.BOT_PANEL_BOT_TOKEN)
    else:
        ctrl_bot = my_bot
    register_handlers(ctrl_bot)

    def _panel_poll_loop():
        while True:
            try:
                updates = ctrl_bot.get_updates(
                    offset=ctrl_bot.last_update_id + 1,
                    timeout=10,
                    allowed_updates=["message", "callback_query"],
                )
                if updates:
                    ctrl_bot.process_new_updates(updates)
            except Exception as e:
                logger.error(f"Panel poll error: {e}")
                time.sleep(5)

    t = threading.Thread(target=_panel_poll_loop, daemon=True)
    t.start()
    logger.info("Control panel enabled (background polling).")


# ---------------------------------<< Main Section >>---------------------------------
if __name__ == "__main__":
    LOCK_PATH = os.path.join(set_path.base_path, "bot.lock")
    for attempt in range(3):
        try:
            with open(LOCK_PATH, "x") as f:
                f.write(str(os.getpid()))
            break
        except FileExistsError:
            try:
                os.remove(LOCK_PATH)
                with open(LOCK_PATH, "x") as f:
                    f.write(str(os.getpid()))
                break
            except (FileExistsError, OSError):
                if attempt < 2:
                    import time
                    time.sleep(1)
                else:
                    logger.error("Another bot instance is already running. Exiting.")
                    sys.exit(1)
        except OSError:
            logger.error("Cannot create lock file. Exiting.")
            sys.exit(1)

    def _remove_lock():
        try:
            os.remove(LOCK_PATH)
        except Exception:
            pass

    atexit.register(_remove_lock)

    db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    db_conn.execute("PRAGMA journal_mode=WAL")
    db_conn.execute("PRAGMA busy_timeout=5000")

    logger.info(f"Bot started! Running every {NEWS_UPDATE_INTERVAL_MINUTES} minutes...")

    def job():
        try:
            logger.info("Starting scheduled news fetch...")
            main()
            logger.info(green("Scheduled run completed."))
        except Exception as e:
            logger.exception(f"Error occurred in job: {e}")

    def _sleep_and_panel(seconds):
        if seconds <= 0:
            return
        for _ in range(seconds // 2):
            time.sleep(2)

    def _next_aligned_seconds():
        now = datetime.now()
        total_sec = now.minute * 60 + now.second
        interval_sec = NEWS_UPDATE_INTERVAL_MINUTES * 60
        return (interval_sec - (total_sec % interval_sec)) % interval_sec

    job()
    delay = _next_aligned_seconds()
    if delay == 0:
        delay = NEWS_UPDATE_INTERVAL_MINUTES * 60
    logger.info(f"Next run in {delay // 60}m {delay % 60}s")
    _sleep_and_panel(delay)

    while True:
        try:
            job()
            delay = _next_aligned_seconds()
            if delay == 0:
                delay = NEWS_UPDATE_INTERVAL_MINUTES * 60
            _sleep_and_panel(delay)
        except Exception as e:
            logger.exception(f"Fatal loop error: {e}")
            _remove_lock()
            time.sleep(30)
