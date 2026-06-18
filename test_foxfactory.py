import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date
import json
import re

# Manually load main.env
with open("main.env", encoding="utf-8") as f:
    env_text = f.read()

def get_env(key):
    m = re.search(rf"^{key}\s*=\s*'(.*?)'", env_text, re.MULTILINE | re.DOTALL)
    if not m:
        m = re.search(rf"^{key}\s*=\s*\"(.*?)\"", env_text, re.MULTILINE | re.DOTALL)
    if not m:
        m = re.search(rf"^{key}\s*=\s*(\S+)", env_text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""

HIGH_IMPACT_KEYWORDS = json.loads(get_env("HIGH_IMPACT_KEYWORDS"))
MIN_IMPACT_SCORE = int(get_env("MIN_IMPACT_SCORE"))

IMPACT_BONUS = {"High": 5, "Medium": 3, "Low": 1, "Holiday": 0}

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

resp = requests.get(URL, timeout=15, headers=headers)
if resp.status_code == 429:
    print("Rate limited (429). Using cached response...\n")
    with open("ff_cache.xml", "r", encoding="utf-8") as f:
        raw = f.read()
else:
    resp.raise_for_status()
    raw = resp.content.decode("windows-1252", errors="replace")
    with open("ff_cache.xml", "w", encoding="utf-8") as f:
        f.write(raw)
root = ET.fromstring(raw)

today_str = date.today().strftime("%m-%d-%Y")
print(f"Today: {today_str}\n")

def parse_num(raw):
    raw = raw.strip().replace("%", "").replace(",", "")
    for suf, mul in [("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if raw.endswith(suf):
            try: return float(raw[:-1]) * mul
            except: pass
    try: return float(raw)
    except: return None

events = []
for event in root.findall("event"):
    title = event.findtext("title", "")
    country = event.findtext("country", "")
    date_str = event.findtext("date", "")
    time_str = event.findtext("time", "")
    impact = event.findtext("impact", "")
    forecast = event.findtext("forecast", "") or ""
    previous = event.findtext("previous", "") or ""
    url = event.findtext("url", "")

    text_lower = (title + " " + country).lower()
    kw_score = 0
    matched = []
    for kw, val in HIGH_IMPACT_KEYWORDS.items():
        if kw.lower() in text_lower:
            kw_score += val
            matched.append(kw)

    imp_bonus = IMPACT_BONUS.get(impact, 0)
    total_score = kw_score + imp_bonus
    is_today = date_str == today_str

    f = parse_num(forecast)
    p = parse_num(previous)
    if f is not None and p is not None and p != 0:
        pct_change = ((f - p) / abs(p)) * 100
        direction = "Bullish ↗" if pct_change > 0 else "Bearish ↘" if pct_change < 0 else "Neutral →"
    else:
        pct_change = None
        direction = "N/A"

    events.append({
        "title": title,
        "country": country,
        "date": date_str,
        "time": time_str,
        "impact": impact,
        "forecast": forecast or "N/A",
        "previous": previous or "N/A",
        "url": url,
        "kw_score": kw_score,
        "imp_bonus": imp_bonus,
        "total_score": total_score,
        "matched": matched,
        "is_today": is_today,
        "direction": direction,
        "pct_change": pct_change,
    })

events.sort(key=lambda x: (not x["is_today"], -x["total_score"]))

print(f"Total events: {len(events)}")
print(f"MIN_IMPACT_SCORE = {MIN_IMPACT_SCORE} (from main.env)")
print(f"Events passing: {sum(1 for e in events if e['total_score'] >= MIN_IMPACT_SCORE)}\n")

print(f"{'PASS':6s} {'Score':6s} {'Day':10s} {'Curr':5s} {'Impact':8s} Event")
print("-" * 100)

for e in events:
    passes = "✅ PASS" if e["total_score"] >= MIN_IMPACT_SCORE else "   —"
    day_label = "TODAY" if e["is_today"] else e["date"]
    print(f"{passes:6s} {e['total_score']:4d}  "
          f"{day_label:10s} {e['country']:5s} {e['impact']:8s} {e['title']}")

print()
print("=" * 100)
print("TOP SCORED EVENTS:\n")

top = [e for e in events if e["total_score"] >= MIN_IMPACT_SCORE]
if not top:
    top = events[:10]

for e in top:
    badge = "● TODAY" if e["is_today"] else "      "
    print(f"  {badge} Score: {e['total_score']:2d} "
          f"(kw:{e['kw_score']}+imp:{e['imp_bonus']}) | "
          f"[{e['country']:4s}] {e['impact']:6s} | {e['title']}")
    print(f"         Date   : {e['date']} {e['time']}")
    print(f"         Forcast: {e['forecast']:12s} | Prev: {e['previous']:12s} | {e['direction']}")
    if e["pct_change"] is not None:
        print(f"         Market  : {'📈' if e['pct_change'] > 0 else '📉'} Expected change: {e['pct_change']:+.1f}%")
    if e["matched"]:
        print(f"         Matched: {', '.join(e['matched'])}")
    print(f"         URL    : {e['url']}")
    print()
