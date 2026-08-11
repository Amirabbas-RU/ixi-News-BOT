"""Send today's snapshot image + caption (new footer format) to t.me/ixi_flower via user session."""
import asyncio
import os
import sys

# Proxy for OpenRouter caption generation
os.environ["HTTP_PROXY"] = "socks5h://127.0.0.1:10808"
os.environ["HTTPS_PROXY"] = "socks5h://127.0.0.1:10808"
os.environ["http_proxy"] = "socks5h://127.0.0.1:10808"
os.environ["https_proxy"] = "socks5h://127.0.0.1:10808"

sys.path.insert(0, "/home/ixi_flower/Documents/ixi-News-BOT")
import set_path
import config
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from openrouter_summarizer import generate_daily_calendar_caption

CALENDAR_TZ = ZoneInfo(config.CALENDAR_TIMEZONE)
TEHRAN_TZ = ZoneInfo("Asia/Tehran")


def parse_forex_datetime(date_str: str, time_str: str):
    for fmt in ["%m-%d-%Y %I:%M%p", "%m-%d-%Y %H:%M"]:
        try:
            naive = datetime.strptime(f"{date_str} {time_str}", fmt)
            return naive.replace(tzinfo=CALENDAR_TZ)
        except ValueError:
            continue
    return None


def get_today_calendar_events():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, country, event_date, event_time, impact, "
        "forecast, previous, title_fa FROM forex_events "
        "WHERE result_sent = 0 OR result_sent IS NULL "
        "ORDER BY event_date, event_time"
    )
    rows = [dict(r) for r in cur.fetchall()]
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
                ai_caption += f"\n{build_date_caption(now_utc)}\n💎💎 @ForexEyvazi 💎💎"
                return ai_caption
    except Exception:
        import traceback
        traceback.print_exc()
    return None


async def main():
    now_utc = datetime.now(timezone.utc)
    caption = build_snapshot_caption(now_utc)
    if not caption:
        caption = build_date_caption(now_utc) + "\n💎💎 @ForexEyvazi 💎💎"
    print(f"CAPTION_LEN={len(caption)}", flush=True)

    from telethon import TelegramClient
    import socks
    client = TelegramClient(
        "/home/ixi_flower/.hermes/scripts/telegram-session",
        23420648,
        "4bf23b731eaec21a8ce440230e6c4457",
        proxy=(socks.SOCKS5, "127.0.0.1", 10808),
    )
    await client.connect()
    me = await client.get_me()
    print(f"AUTH_OK={me.first_name} @{me.username}", flush=True)

    entity = await client.get_entity("https://t.me/ixi_flower")
    print(f"ENTITY: id={entity.id} title={getattr(entity, 'title', None)}", flush=True)

    await client.send_file(entity, "/home/ixi_flower/Documents/ixi-News-BOT/test_snapshot_today.png", caption=caption)
    print("SENT_OK", flush=True)
    await client.disconnect()


asyncio.run(main())
