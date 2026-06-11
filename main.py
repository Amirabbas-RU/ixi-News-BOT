import set_path
import config
import init_database
import os
import schedule
import time
import telebot
import sqlite3
from logger import logger
import re

from sources_cnbc import CNBCRSS
from sources_yahoo import YahooRSS
from sources_forexfactory import ForexFactoryCalendar

from openrouter_summarizer import summarize_news_fa

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

HIGH_IMPACT_KEYWORDS = config.HIGH_IMPACT_KEYWORDS
SOURCE_SCORE = config.SOURCE_SCORE


# ---------------------------------<< sent today cache (prevents duplicate sends across restarts) >>---------------------------------
import json
from datetime import date

SENT_CACHE_PATH = os.path.join(os.path.dirname(DB_PATH), "sent_cache.json")


def load_sent_cache() -> set:
    try:
        with open(SENT_CACHE_PATH) as f:
            data = json.load(f)
        if data.get("date") == str(date.today()):
            return set(data.get("urls", []))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return set()


def save_sent_cache(urls: set):
    with open(SENT_CACHE_PATH, "w") as f:
        json.dump({"date": str(date.today()), "urls": list(urls)}, f)


def was_sent_today(url: str) -> bool:
    return url in load_sent_cache()


def mark_sent_today(url: str):
    cache = load_sent_cache()
    cache.add(url)
    save_sent_cache(cache)


# ---------------------------------<< setup telegram bot >>---------------------------------
my_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
bot_username = my_bot.get_me().username

# ---------------------------------<< optional control panel >>---------------------------------
if config.BOT_PANEL:
    import threading
    from control_bot import register_handlers

    if config.BOT_PANEL_BOT_TOKEN:
        ctrl_bot = telebot.TeleBot(config.BOT_PANEL_BOT_TOKEN)
        register_handlers(ctrl_bot)
        ctrl_bot_name = ctrl_bot.get_me().username
    else:
        ctrl_bot = my_bot
        register_handlers(ctrl_bot)

    def _poll():
        try:
            ctrl_bot.infinity_polling()
        except Exception as e:
            logger.error(f"Control panel polling error: {e}")

    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    logger.info("Control panel enabled (polling in background thread).")


# ---------------------------------<< program main body >>---------------------------------
def insert_news(news: dict) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM news WHERE url = ? LIMIT 1", (news["url"],))
        exists = cursor.fetchone()

        if exists:
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
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Insert failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


def update_news_summary(news_id: int, summary: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE news
                SET summary = ?
                WHERE id = ?
            """,
                (summary, news_id),
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error in update_news_summary: {e}")
        raise


def get_unsent_high_score_news(threshold: float = 7.0):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, title, content, source, importance_score, image_url, url,
               published_at
        FROM news
        WHERE importance_score >= ?
            AND published = 0
        ORDER BY importance_score DESC
    """,
        (threshold,),
    )

    rows = cursor.fetchall()
    conn.close()

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
                "published_at": row[7],
            }
        )
    return news_list


def mark_news_as_summarized(news_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE news
        SET summarized = 1
        WHERE id = ?
    """,
        (news_id,),
    )

    conn.commit()
    conn.close()


def mark_news_as_sent(news_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE news
        SET published = 1
        WHERE id = ?
    """,
        (news_id,),
    )

    conn.commit()
    conn.close()


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
    if news_item.get("source") == "ForexFactory":
        content = news_item.get("content", "")
        if "Impact: High" in content:
            score += 8
        elif "Impact: Medium" in content:
            score += 3
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
                    parse_mode="MarkdownV2",
                )
            else:
                bot.send_message(chat_id=chat_id, text=content, parse_mode="MarkdownV2")

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


# ---------------------------------<< helper send function >>---------------------------------
def _send_news(news_id, source, message_text, image_url):
    success = False
    try:
        if image_url:
            caption = message_text[:1024] if len(message_text) > 1024 else message_text
            success = send_with_retry(
                bot=my_bot,
                chat_id=TELEGRAM_CHANNEL_ID,
                content=caption,
                image_url=image_url,
                max_retries=3,
            )

        if not success:
            logger.info(
                f"Image failed for News ID {news_id} [{source}], "
                f"retrying without image..."
            )
            success = send_with_retry(
                bot=my_bot,
                chat_id=TELEGRAM_CHANNEL_ID,
                content=message_text,
                image_url=None,
                max_retries=2,
            )

        if success:
            logger.info(
                f"News ID {news_id} [{source}] sent to Telegram successfully"
            )
        else:
            logger.error(f"Failed to send news ID {news_id} after all retries")

    except Exception as e:
        logger.error(
            f"Unexpected error during sending for news ID {news_id}: {e}"
        )

    return success


# ---------------------------------<< Main Function >>---------------------------------
def main():
    try:
        sources = [
            CNBCRSS(),
            YahooRSS(),
            ForexFactoryCalendar(),
            # ReutersRSS(),
            # InvestingRSS(),
        ]

        feed_counts = []
        total_new = 0

        for source in sources:
            news_items = source.fetch()
            feed_counts.append((source.name, len(news_items)))
            for news in news_items:
                inserted = insert_news(news)
                if inserted:
                    total_new += 1

        print("── Feed Results ──")
        for name, count in feed_counts:
            print(f"  {name:<20} {count:>4} items")
        print(f"  {'─' * 26}")
        print(f"  {'Total new':<20} {total_new:>4}")
        print()

        # ---------- Score news ----------
        conn = None
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, content, source FROM news WHERE importance_score IS NULL"
                )
                rows = cursor.fetchall()

                for row in rows:
                    news_id, title, content, source = row
                    news_item = {"title": title, "content": content, "source": source}
                    score = calculate_total_score(news_item)
                    cursor.execute(
                        "UPDATE news SET importance_score = ? WHERE id = ?",
                        (score, news_id),
                    )

                conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")

        logger.info("Importance scores updated for new news")

        # ---------- Summarize news with OpenRouter ----------
        high_score_news = get_unsent_high_score_news(threshold=MIN_IMPACT_SCORE)

        if not high_score_news:
            logger.info("No high-score news to process")
            return

        groups = {}
        for news in high_score_news:
            key = (news.get("published_at", ""), news.get("source", ""))
            groups.setdefault(key, []).append(news)

        sorted_groups = sorted(
            groups.items(),
            key=lambda kv: max(n["importance_score"] for n in kv[1]),
            reverse=True,
        )

        final_order = []
        consecutive = 0
        last_source = None
        remaining = list(sorted_groups)

        while remaining and len(final_order) < config.MAX_POSTS_PER_DAY:
            picked = None
            for i, (key, _) in enumerate(remaining):
                source = key[1]
                if source != last_source or consecutive < 3:
                    picked = i
                    break

            if picked is None:
                consecutive = 0
                continue

            key, group = remaining.pop(picked)
            source = key[1]

            if source == last_source:
                consecutive += 1
            else:
                consecutive = 1
                last_source = source

            final_order.append((key, group))

        group_list = final_order

        sent_news = 0
        total_to_send = sum(len(g) for _, g in group_list)
        already_sent_count = 0
        summarization_fail_count = 0
        short_summary_count = 0

        for key, group in group_list:
            publish_time = key[0]
            source_name = key[1]

            if len(group) == 1:
                news = group[0]
                news_id = news.get("id")
                title = news.get("title")
                content = news.get("content")
                news_url = news.get("url", "")

                if news_url and was_sent_today(news_url):
                    already_sent_count += 1
                    mark_news_as_sent(news_id)
                    sent_news += 1
                    continue

                result = summarize_news_fa(title, content)
                if not result:
                    summarization_fail_count += 1
                    continue

                title_fa = result.get("title_fa")
                summary_fa = result.get("summary_fa")

                if len(summary_fa.strip()) < 60:
                    short_summary_count += 1
                    continue

                try:
                    update_news_summary(news_id, summary_fa)
                    mark_news_as_summarized(news_id)
                except Exception as e:
                    logger.error(
                        f"Database update error for news ID {news_id}: {e}"
                    )
                    continue

                safe_title = escape_markdown_v2(title_fa)
                safe_summary = escape_markdown_v2(summary_fa)
                message_text = f"*{safe_title}*\n\n{safe_summary}\n\n💎💎 ||*HAMID EYVAZI*|| 💎💎"
                image_url = news.get("image_url")

                success = _send_news(news_id, source_name, message_text, image_url)
                if success:
                    mark_news_as_sent(news_id)
                    mark_sent_today(news_url)
                    sent_news += 1

                time.sleep(10)
                continue

            all_ids = [n["id"] for n in group]
            all_urls = [n["url"] for n in group if n.get("url")]

            already_sent = any(was_sent_today(u) for u in all_urls if u)
            if already_sent:
                for n in group:
                    mark_news_as_sent(n["id"])
                    sent_news += 1
                already_sent_count += len(group)
                continue

            combined_titles = " | ".join(n["title"] for n in group)
            combined_content = "\n\n".join(n["content"] for n in group)
            result = summarize_news_fa(combined_titles, combined_content)
            if not result:
                summarization_fail_count += len(group)
                continue

            title_fa = result.get("title_fa")
            summary_fa = result.get("summary_fa")

            if len(summary_fa.strip()) < 60:
                short_summary_count += len(group)
                continue

            for n in group:
                try:
                    update_news_summary(n["id"], summary_fa)
                    mark_news_as_summarized(n["id"])
                except Exception as e:
                    logger.error(
                        f"Database update error for news ID {n['id']}: {e}"
                    )

            safe_title = escape_markdown_v2(title_fa)
            safe_summary = escape_markdown_v2(summary_fa)
            message_text = f"*{safe_title}*\n\n{safe_summary}\n\n💎💎 ||*HAMID EYVAZI*|| 💎💎"

            image_url = group[0].get("image_url")
            success = _send_news(all_ids, source_name, message_text, image_url)
            if success:
                for n in group:
                    mark_news_as_sent(n["id"])
                    if n.get("url"):
                        mark_sent_today(n["url"])
                sent_news += len(group)

            time.sleep(10)

        actual_sent = sent_news - already_sent_count
        print("─" * 55)
        if actual_sent:
            print(f"  ✓ {actual_sent} news sent to Telegram")
        if already_sent_count:
            print(f"  ⚠ {already_sent_count} already sent today (skipped)")
        if summarization_fail_count:
            print(f"  ⚠ {summarization_fail_count} summarization failed (skipped)")
        if short_summary_count:
            print(f"  ⚠ {short_summary_count} summary too short (skipped)")
        remaining = total_to_send - sent_news
        if remaining:
            print(f"  ⚠ {remaining} not processed (limit reached or errors)")
        print("─" * 55)

    except Exception as e:
        logger.exception(f"Error in main function: {e}")
        raise


# ---------------------------------<< Main Section >>---------------------------------
if __name__ == "__main__":
    logger.info(f"Bot started! Running every {NEWS_UPDATE_INTERVAL_MINUTES} minutes...")

    def job():
        try:
            logger.info("Starting scheduled news fetch...")
            main()
            logger.info("Scheduled run completed.")
        except Exception as e:
            logger.exception(f"Error occurred in job: {e}")

    schedule.every(NEWS_UPDATE_INTERVAL_MINUTES).minutes.do(job)

    job()

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            logger.exception(f"Fatal loop error: {e}")
            time.sleep(60)
