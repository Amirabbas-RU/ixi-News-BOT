"""Test: generate today's snapshot image + caption (with new footer) and send to @ixi_flower_R."""
import os
os.environ["HTTP_PROXY"] = "socks5h://127.0.0.1:10808"
os.environ["HTTPS_PROXY"] = "socks5h://127.0.0.1:10808"
os.environ["http_proxy"] = "socks5h://127.0.0.1:10808"
os.environ["https_proxy"] = "socks5h://127.0.0.1:10808"

import set_path
import config
import sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import telebot
from openrouter_summarizer import generate_daily_calendar_caption
from forex_image_generator import generate_forex_images

CALENDAR_TZ = ZoneInfo(config.CALENDAR_TIMEZONE)
TEHRAN_TZ = ZoneInfo("Asia/Tehran")


def parse_forex_datetime(date_str: str, time_str: str):
    formats = ["%m-%d-%Y %I:%M%p", "%m-%d-%Y %H:%M"]
    for fmt in formats:
        try:
            naive = datetime.strptime(f"{date_str} {time_str}", fmt)
            return naive.replace(tzinfo=CALENDAR_TZ)
        except ValueError:
            continue
    return None


def get_today_calendar_events():
    cols = [
        "id", "title", "country", "event_date", "event_time", "impact",
        "forecast", "previous", "url", "alert_pre_sent", "alert_15min_sent",
        "alert_30min_sent", "result_sent", "news_inserted", "analysis",
        "created_at", "title_fa", "alert_message_id",
    ]
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, country, event_date, event_time, impact, "
        "forecast, previous, url, alert_pre_sent, alert_15min_sent, "
        "alert_30min_sent, result_sent, news_inserted, analysis, "
        "created_at, title_fa, alert_message_id "
        "FROM forex_events "
        "WHERE result_sent = 0 OR result_sent IS NULL "
        "ORDER BY event_date, event_time"
    )
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    today_tehran = datetime.now(TEHRAN_TZ).date()
    today_events = []
    for ev in rows:
        ev_dt = parse_forex_datetime(ev["event_date"], ev["event_time"])
        if ev_dt is None:
            continue
        ev_tehran = ev_dt.astimezone(TEHRAN_TZ)
        if ev_tehran.date() == today_tehran:
            ev["event_time"] = ev_tehran.strftime("%H:%M")
            today_events.append(ev)

    today_events.sort(key=lambda e: (
        parse_forex_datetime(e["event_date"], e["event_time"]) or datetime.min.replace(tzinfo=TEHRAN_TZ),
        {"Low": 0, "Medium": 1, "High": 2}.get(e.get("impact", ""), 0),
    ))
    return today_events


def build_date_caption(now_utc: datetime) -> str:
    weekdays_fa = ["دوشنبه", "سه\u200cشنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
    months_en_fa = {
        1: "ژانویه", 2: "فوریه", 3: "مارس", 4: "آوریل",
        5: "مه", 6: "ژوئن", 7: "جولای", 8: "اوت",
        9: "سپتامبر", 10: "اکتبر", 11: "نوامبر", 12: "دسامبر",
    }
    tehran_dt = now_utc.astimezone(TEHRAN_TZ)
    wd = weekdays_fa[tehran_dt.weekday()]
    day = tehran_dt.day
    month_en = months_en_fa[tehran_dt.month]
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
        return f"📅 تقویم اقتصادی {wd} {day} {month_en} | {jalali_str}"
    return f"📅 تقویم اقتصادی {wd} {day} {month_en}"


def build_snapshot_caption(now_utc: datetime) -> str:
    date_header = build_date_caption(now_utc)
    try:
        today_events = get_today_calendar_events()
        if today_events:
            ai_caption = generate_daily_calendar_caption(today_events, date_header)
            if ai_caption:
                if len(ai_caption) > 950:
                    positions = [i for i, ch in enumerate(ai_caption) if ch == "📣" and (i == 0 or ai_caption[i-1] != "📣")]
                    last_good = 0
                    for pos in positions:
                        if pos < 900:
                            last_good = pos
                        else:
                            break
                    if last_good > 500:
                        ai_caption = ai_caption[:last_good].rstrip()
                    else:
                        ai_caption = ai_caption[:947]
                # Append date footer + channel tag (NEW FORMAT)
                ai_caption += f"\n\n{build_date_caption(now_utc)}\n💎💎 @ForexEyvazi 💎💎"
                return ai_caption
    except Exception as e:
        import traceback
        traceback.print_exc()
    return None


now_utc = datetime.now(timezone.utc)

# 1) Generate today's snapshot image
paths = generate_forex_images(
    db_path=config.DB_PATH,
    output_path="test_snapshot_today.png",
    cal_tz=config.CALENDAR_TIMEZONE,
)
print(f"Images: {paths}")
if not paths:
    print("NO IMAGE — no today events")
    raise SystemExit(1)

# 2) Build caption
caption = build_snapshot_caption(now_utc)
if not caption:
    caption = build_date_caption(now_utc) + "\n💎💎 @ForexEyvazi 💎💎"
print(f"Caption chars: {len(caption)}")
print("----- CAPTION -----")
print(caption)
print("----- END -----")

# 3) Resolve @ixi_flower chat id (the bot's own channel IxI_chanle = -1002048495961)
bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN)
chat = bot.get_chat("@ixi_flower")
print(f"Target chat: id={chat.id} type={chat.type} title={getattr(chat, 'title', None)}")

# 4) Send
with open(paths[0], "rb") as f:
    msg = bot.send_photo(chat_id=chat.id, photo=f, caption=caption, timeout=20)
print(f"SENT message_id={msg.message_id} chat_id={chat.id}")
