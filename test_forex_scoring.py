import sys, os

sys.path.insert(0, os.path.dirname(__file__))
import config
from sources_forexfactory import ForexFactoryCalendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def filter_events(events, days_back=None, days_ahead=None):
    """Filter events by date range. Pass days_back=0, days_ahead=0 for today only."""
    if days_back is None and days_ahead is None:
        return events

    tz = ZoneInfo(config.CALENDAR_TIMEZONE)
    now = datetime.now(tz).date()

    start = now + timedelta(days=-(days_back or 0))
    end = now + timedelta(days=(days_ahead or 0))

    filtered = []
    for ev in events:
        try:
            dt = datetime.strptime(f"{ev['date']} {ev['time']}", "%m-%d-%Y %I:%M%p")
        except:
            try:
                dt = datetime.strptime(f"{ev['date']} 12:00AM", "%m-%d-%Y %I:%M%p")
            except:
                continue
        ev_date = dt.date()
        if start <= ev_date <= end:
            filtered.append(ev)
    return filtered


def main():
    cal = ForexFactoryCalendar()
    events = cal.fetch()
    if not events:
        print("No data. RSS rate limited and no cache.")
        return

    FOREX_MIN = config.FOREX_MIN_SCORE
    ALERT_IMPACTS = {x.strip() for x in config.FOREX_ALERT_IMPACTS.split(",")}
    KW = config.HIGH_IMPACT_KEYWORDS

    # ========== FILTER: change these to your needs ==========
    # Set both to 0 for today only
    # Set days_back=7 for last 7 days, days_ahead=0 for past week only
    # Comment both out to see all events
    # days_back = 0
    # days_ahead = 7

    # days_back = 0     # today only
    # days_ahead = 0
    #
    # # For last 7 days:
    # days_back = 7
    # days_ahead = 0
    #
    # # For next 3 days:
    days_back = 0
    days_ahead = 3
    #
    # # For full week (past 3 + next 4):
    # days_back = 3
    # days_ahead = 4
    # =======================================================

    filtered = filter_events(events, days_back=days_back, days_ahead=days_ahead)

    if len(filtered) != len(events):
        tz = ZoneInfo(config.CALENDAR_TIMEZONE)
        now = datetime.now(tz).date()
        start = now + timedelta(days=-(days_back or 0))
        end = now + timedelta(days=(days_ahead or 0))
        print(
            f"  Date filter: {start} to {end}  ({len(filtered)} of {len(events)} events)"
        )

    cal_tz = ZoneInfo(config.CALENDAR_TIMEZONE)
    local_tz = ZoneInfo("Asia/Tehran")
    now_local = datetime.now(local_tz)

    def score(item):
        s = 0
        text = (
            item.get("title", "") + " " + item.get("content", item.get("title", ""))
        ).lower()
        for kw, val in KW.items():
            if kw.lower() in text:
                s += val
        s += config.SOURCE_SCORE.get("ForexFactory", 0)
        return s

    def parse_dt_safe(ev):
        try:
            dt = datetime.strptime(f"{ev['date']} {ev['time']}", "%m-%d-%Y %I:%M%p")
        except:
            dt = datetime.strptime(f"{ev['date']} 12:00AM", "%m-%d-%Y %I:%M%p")
        return dt.replace(tzinfo=cal_tz)

    sorted_events = sorted(filtered, key=lambda ev: parse_dt_safe(ev))

    print(f"{'=' * 150}")
    print(f"  FOREX MIN SCORE:    {FOREX_MIN}")
    ALERT_IMPACTS_FMT = ", ".join(sorted(ALERT_IMPACTS))
    print(f"  ALERT IMPACTS:      {ALERT_IMPACTS_FMT}")
    print(f"  Keywords loaded:    {len(KW)} keywords")
    print(f"  Events:             {len(sorted_events)}")
    print(f"  Now (Tehran):       {now_local.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 150}")
    print(
        f"{'TITLE':<43} {'CNTRY':<6} {'IMPACT':<8} {'SCORE':<6} {'ALERT?':<8} {'NY':<10} {'TEH':<10} {'MIN':<7} {'FORECAST':<14} {'PREVIOUS':<14} {'MATCHED'}"
    )
    print("-" * 150)

    alert_count = 0
    for ev in sorted_events:
        title = ev["title"]
        s = score({"title": title, "content": title, "source": "ForexFactory"})
        passes = ev["impact"] in ALERT_IMPACTS and s >= FOREX_MIN
        dt = parse_dt_safe(ev)
        dt_local = dt.astimezone(local_tz)
        mins_left = round((dt - datetime.now().astimezone()).total_seconds() / 60)
        mins_str = (
            f"{mins_left}m"
            if mins_left > 0
            else f"{abs(mins_left)}m ago"
            if mins_left < 0
            else "now"
        )
        kw_matches = []
        tl = title.lower()
        for kw, val in sorted(KW.items(), key=lambda x: -x[1]):
            if kw.lower() in tl:
                kw_matches.append(f"{kw}(+{val})")
        kw_str = ", ".join(kw_matches[:3]) if kw_matches else "-"
        forecast = ev.get("forecast", "-") or "-"
        previous = ev.get("previous", "-") or "-"
        if passes:
            alert_count += 1
        print(
            f"{title:<43} {ev['country']:<6} {ev['impact']:<8} {s:<6} {'✅' if passes else '─':<8}"
            f"{dt.strftime('%I:%M%p'):<10} {dt_local.strftime('%H:%M'):<10} {mins_str:<7}"
            f"{forecast:<14} {previous:<14} {kw_str}"
        )

    print("-" * 150)
    print(f"  Total: {len(filtered)}  |  ALERTS: {alert_count}")
    print(f"  {'=' * 150}")


if __name__ == "__main__":
    main()
