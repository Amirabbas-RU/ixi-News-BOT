
import set_path
import config
import init_database
import os
import time
import telebot
import sqlite3
from logger import logger
import re

from sources_cnbc import CNBCRSS
from sources_yahoo import YahooRSS

from openrouter_summarizer import summarize_news_fa, summarize_forex_event_fa
from sources_forexfactory import ForexFactoryCalendar
from datetime import datetime
from zoneinfo import ZoneInfo

#---------------------------------<< in order to avoid freeze .exe file >>---------------------------------
import multiprocessing
if __name__ == "__main__":
    multiprocessing.freeze_support()

#---------------------------------<< define global variables and load data >>---------------------------------
NEWS_UPDATE_INTERVAL_MINUTES = config.NEWS_UPDATE_INTERVAL_MINUTES

DB_NAME = config.DB_NAME
DB_PATH = config.DB_PATH

OPENROUTER_API_KEY  = config.OPENROUTER_API_KEY
OPENROUTER_MODEL    = config.OPENROUTER_MODEL
OPENROUTER_BASE_URL = config.OPENROUTER_BASE_URL

TELEGRAM_BOT_TOKEN  = config.TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL_ID = config.TELEGRAM_CHANNEL_ID

MIN_IMPACT_SCORE    = config.MIN_IMPACT_SCORE
FOREX_MIN_SCORE     = config.FOREX_MIN_SCORE

HIGH_IMPACT_KEYWORDS = config.HIGH_IMPACT_KEYWORDS
SOURCE_SCORE = config.SOURCE_SCORE

FOREXFACTORY_CALENDAR_URL = config.FOREXFACTORY_CALENDAR_URL
CALENDAR_TZ = ZoneInfo(config.CALENDAR_TIMEZONE)
FOREX_ALERT_IMPACTS = [x.strip() for x in config.FOREX_ALERT_IMPACTS.split(",")]
FOREX_IMPACT_EMOJIS = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
FOREX_IMPACT_LABELS = {"High": "بالا", "Medium": "متوسط", "Low": "پایین"}


#---------------------------------<< setup telegram bot >>---------------------------------
my_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
bot_username = my_bot.get_me().username 


#---------------------------------<< program main body >>---------------------------------
def insert_news(news: dict) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT 1 FROM news WHERE url = ? LIMIT 1",
            (news["url"],)
        )
        exists = cursor.fetchone()

        if exists:
            return False

        cursor.execute("""
        INSERT INTO news (title, url, image_url, source, published_at, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            news["title"],
            news["url"],
            news["image_url"],
            news["source"],
            news["published_at"],
            news["content"]
        ))
        conn.commit()
        return True
    except Exception  as e:
        logger.warning(f"Insert failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


def update_news_summary(news_id: int, summary: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE news
                SET summary = ?
                WHERE id = ?
            """, (summary, news_id))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in update_news_summary: {e}")
        raise


def get_unsent_high_score_news(threshold: float = 7.0, source: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = """
        SELECT id, title, content, source, importance_score, image_url
        FROM news
        WHERE importance_score >= ?
            AND published = 0
    """
    params = [threshold]
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY importance_score DESC"
    cursor.execute(query, params)

    rows = cursor.fetchall()
    conn.close()

    news_list = []
    for row in rows:
        news_list.append({
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "source": row[3],
            "importance_score": row[4],
            "image_url": row[5]
        })
    return news_list


def mark_news_as_summarized(news_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE news
        SET summarized = 1
        WHERE id = ?
    """, (news_id,))

    conn.commit()
    conn.close()

def mark_news_as_sent(news_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE news
        SET published = 1
        WHERE id = ?
    """, (news_id,))

    conn.commit()
    conn.close()


#---------------------------------<< news scoring section >>---------------------------------
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


def send_with_retry(bot, chat_id, content, image_url=None, max_retries=3):
    """
    ارسال پیام به تلگرام با قابلیت retry
    
    Args:
        bot: شیء تلگرام بات
        chat_id: آیدی کانال/چت
        content: محتوای پیام
        image_url: آدرس تصویر (اختیاری)
        max_retries: حداکثر تعداد تلاش‌ها
    
    Returns:
        bool: موفقیت آمیز بودن ارسال
    """
    retry_delays = [2, 5, 10]  # تاخیرها به ثانیه
    
    for attempt in range(max_retries):
        try:
            if image_url:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=content,
                    parse_mode="MarkdownV2"
                )
            else:
                bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    parse_mode="MarkdownV2"
                )
            
            logger.info(f"Message sent successfully (attempt {attempt + 1})")
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


#---------------------------------<< Forex Calendar Functions >>---------------------------------
def insert_forex_event(event: dict) -> bool:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM forex_events WHERE url = ? LIMIT 1",
                (event["url"],)
            )
            if cursor.fetchone():
                return False
            cursor.execute("""
                INSERT INTO forex_events (title, country, event_date, event_time, impact, forecast, previous, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["title"], event["country"], event["date"], event["time"],
                event["impact"], event["forecast"], event["previous"], event["url"]
            ))
            conn.commit()
            return True
    except Exception as e:
        logger.warning(f"Insert forex event failed: {e}")
        return False


def get_pending_forex_alerts() -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, country, event_date, event_time, impact,
                       forecast, previous, url, analysis,
                       alert_pre_sent, alert_15min_sent, alert_30min_sent, result_sent, news_inserted
                FROM forex_events
                WHERE news_inserted = 0
                ORDER BY event_date, event_time
            """)
            cols = ["id", "title", "country", "event_date", "event_time", "impact",
                    "forecast", "previous", "url", "analysis",
                    "alert_pre_sent", "alert_15min_sent", "alert_30min_sent", "result_sent", "news_inserted"]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get pending forex alerts error: {e}")
        return []


def mark_forex_alert(alert_type: str, event_id: int):
    col_map = {"pre": "alert_pre_sent", "15min": "alert_15min_sent",
               "30min": "alert_30min_sent", "result": "result_sent", "news": "news_inserted"}
    col = col_map.get(alert_type)
    if not col:
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(f"UPDATE forex_events SET {col} = 1 WHERE id = ?", (event_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Mark forex alert error: {e}")


def update_forex_analysis(event_id: int, analysis: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE forex_events SET analysis = ? WHERE id = ?", (analysis, event_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Update forex analysis error: {e}")


def parse_forex_datetime(date_str: str, time_str: str) -> datetime | None:
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
        return naive.replace(tzinfo=CALENDAR_TZ)
    except Exception as e:
        logger.warning(f"Parse forex datetime failed: {date_str} {time_str} - {e}")
        return None


def send_forex_message(text: str) -> bool:
    for attempt in range(3):
        try:
            my_bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=text, parse_mode=None)
            logger.info("Forex alert sent successfully")
            return True
        except Exception as e:
            logger.warning(f"Forex send attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(3)
    return False


def mark_past_forex_events_done():
    try:
        now_dt = datetime.now().astimezone()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, event_date, event_time FROM forex_events WHERE news_inserted = 0")
            for row in cursor.fetchall():
                ev_id, ev_date, ev_time = row
                ev_dt = parse_forex_datetime(ev_date, ev_time)
                if ev_dt and (ev_dt - now_dt).total_seconds() / 60.0 < -60:
                    conn.execute("UPDATE forex_events SET news_inserted = 1 WHERE id = ?", (ev_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Mark past events error: {e}")


def insert_forex_into_news(ev: dict):
    try:
        title = ev["title"]
        url = ev.get("url", f"https://www.forexfactory.com/calendar?day={ev['event_date']}")
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

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM news WHERE url = ?", (url,))
            if cursor.fetchone():
                return
            cursor.execute("""
                INSERT INTO news (title, url, image_url, source, published_at, content, importance_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, url, None, "ForexFactory", f"{ev['event_date']} {ev['event_time']}", content, importance_score))
            conn.commit()
    except Exception as e:
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


def check_forex_calendar():
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
        logger.info(f"{new_count} new forex events stored")

    mark_past_forex_events_done()

    pending = get_pending_forex_alerts()
    now_dt = datetime.now().astimezone()
    logger.info(f"ForexFactory: {len(pending)} pending events to check")

    for ev in pending:
        ev_dt = parse_forex_datetime(ev["event_date"], ev["event_time"])
        if ev_dt is None:
            logger.warning(f"Forex event '{ev['title']}' on {ev['event_date']} — could not parse time, skipping")
            continue

        minutes_until = (ev_dt - now_dt).total_seconds() / 60.0
        logger.info(f"  [{ev['impact']}] {ev['country']} — {ev['title']} — {ev['event_date']} {ev['event_time']} — {minutes_until:+.0f} min")

        if ev["impact"] not in FOREX_ALERT_IMPACTS:
            logger.info(f"    → Impact '{ev['impact']}' not in alert list, marking as done")
            mark_forex_alert("news", ev["id"])
            continue

        impact_emoji = FOREX_IMPACT_EMOJIS.get(ev["impact"], "⚪")
        impact_label = FOREX_IMPACT_LABELS.get(ev["impact"], "")

        if 0 <= minutes_until <= 30 and not ev["alert_pre_sent"]:
            mins = round(minutes_until)
            logger.info(f"    → Sending pre-alert ({mins} min before release)")
            title_fa_result = summarize_news_fa(ev["title"], "")
            title_fa = title_fa_result.get("title_fa", "") if title_fa_result else ""
            title_line = f"{title_fa} ({ev['title']})" if title_fa else ev["title"]
            forecast = f"📊 پیش‌بینی: {ev['forecast']}" if ev.get("forecast") else ""
            previous = f"📉 قبلی: {ev['previous']}" if ev.get("previous") else ""
            extra = f"\n{forecast}\n{previous}" if (forecast or previous) else ""
            text = (
                f"🔔 هشدار {mins} دقیقه قبل از انتشار\n"
                f"🚦 {ev['country']} {impact_emoji} {impact_label}\n"
                f"🗓 {title_line}{extra}"
            )
            if send_forex_message(text):
                mark_forex_alert("pre", ev["id"])
                logger.info(f"    ✓ Pre-alert sent for '{ev['title']}'")
            else:
                logger.error(f"    ✗ Failed to send pre-alert for '{ev['title']}'")
        elif 0 <= minutes_until <= 30 and ev["alert_pre_sent"]:
            logger.info(f"    → Pre-alert already sent, skipping")

        if minutes_until < -1 and not ev["news_inserted"]:
            logger.info(f"    → Event released, inserting into news table")
            mark_forex_alert("news", ev["id"])
            insert_forex_into_news(ev)

    logger.info("ForexFactory alert check complete")


#---------------------------------<< Main Function >>---------------------------------
def main():
    try:
        check_forex_calendar()

        SOURCE_CLASSES = {
            "CNBC": CNBCRSS,
            "Yahoo": YahooRSS,
        }

        sources = [SOURCE_CLASSES[name]() for name in config.ACTIVE_SOURCES if name in SOURCE_CLASSES]

        total_new = 0

        for source in sources:
            logger.info(f"Fetching news from {source.name}")
            news_items = source.fetch()

            for news in news_items:
                inserted = insert_news(news)
                if inserted:
                    total_new += 1

        logger.info(f"Total new news inserted: {total_new}")

        if not sources:
            logger.info("No news RSS sources enabled")

        # ---------- Score news ----------
        conn = None
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, content, source FROM news WHERE importance_score IS NULL")
                rows = cursor.fetchall()

                for row in rows:
                    news_id, title, content, source = row
                    news_item = {"title": title, "content": content, "source": source}
                    score = calculate_total_score(news_item)
                    cursor.execute("UPDATE news SET importance_score = ? WHERE id = ?", (score, news_id))

                conn.commit()

        except sqlite3.Error as e:
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

                result = summarize_news_fa(title, content)

                if not result or not result.get("title_fa"):
                    logger.warning(f"{batch_label} ID {news_id} — summarization failed, marking as published")
                    mark_news_as_summarized(news_id)
                    mark_news_as_sent(news_id)
                    continue

                title_fa = result.get("title_fa")
                summary_fa = result.get("summary_fa")

                try:
                    update_news_summary(news_id, summary_fa)
                    mark_news_as_summarized(news_id)
                    logger.info(f"{batch_label} ID {news_id} summarized successfully")
                except Exception as e:
                    logger.error(f"Database update error for {batch_label} ID {news_id}: {e}")
                    continue

                safe_title = escape_markdown_v2(title_fa)
                safe_summary = escape_markdown_v2(summary_fa)
                message_text = f"*{safe_title}*\n\n{safe_summary}\n\n💎💎 ||*HAMID EYVAZI*|| 💎💎"

                success = False
                try:
                    if image_url:
                        success = send_with_retry(
                            bot=my_bot, chat_id=TELEGRAM_CHANNEL_ID,
                            content=message_text, image_url=image_url, max_retries=3
                        )
                    if not success:
                        success = send_with_retry(
                            bot=my_bot, chat_id=TELEGRAM_CHANNEL_ID,
                            content=message_text, image_url=None, max_retries=2
                        )
                    if success:
                        mark_news_as_sent(news_id)
                        logger.info(f"{batch_label} ID {news_id} sent to Telegram successfully")
                        sent += 1
                    else:
                        logger.error(f"Failed to send {batch_label} ID {news_id} after all retries")
                except Exception as e:
                    logger.error(f"Unexpected error during sending for {batch_label} ID {news_id}: {e}")

                time.sleep(10)

            if sent == total:
                logger.info(f"All {sent} {batch_label} news sent to Telegram!")
            else:
                logger.warning(f"Sent {sent} out of {total} {batch_label} news. {total - sent} remaining.")


        # ---------- Process RSS news (threshold = MIN_IMPACT_SCORE) ----------
        rss_news = [n for n in get_unsent_high_score_news(threshold=MIN_IMPACT_SCORE)
                    if n["source"] != "ForexFactory"]
        _process_news_batch(rss_news, "RSS")

        # ---------- Process ForexFactory news (threshold = FOREX_MIN_SCORE) ----------
        forex_news = get_unsent_high_score_news(threshold=FOREX_MIN_SCORE, source="ForexFactory")
        _process_news_batch(forex_news, "ForexFactory")

    except Exception as e:
        logger.exception(f"Error in main function: {e}")
        raise



#---------------------------------<< optional control panel >>---------------------------------
ctrl_bot = None
if config.BOT_PANEL:
    from control_bot import register_handlers

    if config.BOT_PANEL_BOT_TOKEN:
        ctrl_bot = telebot.TeleBot(config.BOT_PANEL_BOT_TOKEN)
    else:
        ctrl_bot = my_bot
    register_handlers(ctrl_bot)
    try:
        ctrl_bot.get_updates(offset=-1)
    except Exception:
        pass
    logger.info("Control panel enabled (manual polling in main loop).")


#---------------------------------<< Main Section >>---------------------------------
if __name__ == "__main__":

    logger.info(f"Bot started! Running every {NEWS_UPDATE_INTERVAL_MINUTES} minutes...")

    def job():
        try:
            logger.info("Starting scheduled news fetch...")
            main()
            logger.info("Scheduled run completed.")
        except Exception as e:
            logger.exception(f"Error occurred in job: {e}")
    
    def _process_panel():
        if not ctrl_bot:
            return
        try:
            updates = ctrl_bot.get_updates(
                offset=ctrl_bot.last_update_id + 1,
                timeout=1,
                allowed_updates=["message", "callback_query"],
            )
            if updates:
                ctrl_bot.process_new_updates(updates)
        except Exception as e:
            logger.error(f"Control panel update error: {e}")

    def _sleep_and_panel(seconds):
        if seconds <= 0:
            return
        for _ in range(seconds // 2):
            time.sleep(2)
            _process_panel()

    def _next_aligned_seconds():
        now = datetime.now()
        total_sec = now.minute * 60 + now.second
        interval_sec = NEWS_UPDATE_INTERVAL_MINUTES * 60
        return (interval_sec - (total_sec % interval_sec)) % interval_sec

    first_delay = _next_aligned_seconds()
    logger.info(f"First job in {first_delay // 60}m {first_delay % 60}s (aligned to {NEWS_UPDATE_INTERVAL_MINUTES}-min intervals)")
    _sleep_and_panel(first_delay)

    while True:
        try:
            job()
            delay = _next_aligned_seconds()
            if delay == 0:
                delay = NEWS_UPDATE_INTERVAL_MINUTES * 60
            _sleep_and_panel(delay)
            _process_panel()
        except Exception as e:
            logger.exception(f"Fatal loop error: {e}")
            time.sleep(30)
