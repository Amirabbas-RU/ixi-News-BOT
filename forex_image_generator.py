"""
ForexFactory Events Image Generator — Persian Edition
Generates a dark-themed Persian table image from pending forex events.
Usage:
    python forex_image_generator.py          # standalone — reads DB, saves PNG
    from forex_image_generator import generate_forex_image  # importable for main.py
"""

import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper

# ── Persian text reshaping (no raqm / bidi C ext needed) ──────────
_PERSIAN_RANGE = set(range(0x0590, 0x08FF + 1)) | set(range(0xFB50, 0xFDFF + 1)) | set(range(0xFE70, 0xFEFF + 1))


def _is_persian(c: str) -> bool:
    return ord(c) in _PERSIAN_RANGE


def _rtl_word(w: str) -> bool:
    """True if the first significant char is Persian/Arabic (RTL)."""
    for c in w:
        if c.isalpha() or c.isdigit():
            return _is_persian(c)
    return False


def _reshape_persian(text: str) -> str:
    """Reshape + reorder Persian text for LTR Pillow rendering (no raqm / bidi).

    1. arabic_reshaper connects characters (initial/medial/final forms).
    2. The word order is reversed (RTL text appears right-to-left, so
       for LTR rendering the words must come in reverse order).
    3. Each RTL word is internally reversed for correct LTR glyph order.
    """
    if not text:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        words = reshaped.split(" ")

        # Tag words as RTL or not
        rtl_flags = [_rtl_word(w) for w in words]

        # Count RTL content words (skip pure-symbol words like emoji, arrows)
        content_rtl = sum(1 for w, r in zip(words, rtl_flags) if r)
        content_total = sum(1 for w in words if any(c.isalpha() or c.isdigit() for c in w))
        is_rtl_text = content_rtl > 0 and content_rtl >= content_total // 2

        if is_rtl_text:
            # Reverse word order AND reverse each RTL word internally
            out = []
            for w in reversed(words):
                if _rtl_word(w):
                    rev = w[::-1].translate(str.maketrans("()", ")("))
                    out.append(rev)
                else:
                    out.append(w)
            return " ".join(out)
        else:
            # Mostly LTR text — just reverse internal RTL words
            out = []
            for w in words:
                if _rtl_word(w):
                    rev = w[::-1].translate(str.maketrans("()", ")("))
                    out.append(rev)
                else:
                    out.append(w)
            return " ".join(out)
    except Exception:
        return text

import set_path  # noqa: F401 — ensure CWD is project root
from config import DB_PATH, CALENDAR_TIMEZONE

# lazy import — only used as fallback when title_fa is NULL
_translate_fn = None


def _get_translate_fn():
    global _translate_fn
    if _translate_fn is None:
        from openrouter_summarizer import translate_title_fa
        _translate_fn = translate_title_fa
    return _translate_fn

# ── output path ──────────────────────────────────────────────────
OUTPUT_PATH = os.path.join(set_path.base_path, "forex_events_snapshot.png")

# ── fonts (try bundled first, fallback to system) ─────────────────
import sys
import os
_FONTS_DIR = os.path.join(sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__), "fonts")

def _resolve_font(bundled: str, system: str) -> str:
    p = os.path.join(_FONTS_DIR, bundled)
    return p if os.path.exists(p) else system

VAZIR_BOLD_PATH   = _resolve_font("Vazirmatn-RD-FD-Bold.ttf",   "/usr/share/fonts/vazirmatn/Vazirmatn-RD-FD-Bold.ttf")
VAZIR_REGULAR_PATH= _resolve_font("Vazirmatn-FD-Light.ttf",     "/usr/share/fonts/vazirmatn/Vazirmatn-FD-Light.ttf")
MONO_PATH         = _resolve_font("CaskaydiaMonoNerdFont-Regular.ttf", "/usr/share/fonts/TTF/CaskaydiaMonoNerdFont-Regular.ttf")

# ── colour palette ───────────────────────────────────────────────
BG_COLOR       = (18, 18, 22, 255)
HEADER_BG      = (30, 30, 40, 255)
ROW_ODD        = (24, 24, 32, 255)
ROW_EVEN       = (20, 20, 28, 255)
BORDER_COLOR   = (60, 60, 75, 255)
TEXT_PRIMARY   = (220, 220, 230, 255)
TEXT_SECONDARY = (150, 150, 165, 255)
ACCENT_VIOLET  = (124, 58, 237, 255)       # #7C3AED
IMPACT_HIGH    = (255, 80, 80, 255)        # قرمز
IMPACT_MEDIUM  = (240, 180, 50, 255)       # کهربایی
IMPACT_LOW     = (80, 200, 80, 255)        # سبز
SENT_COLOR     = (100, 200, 100, 255)

# ── Persian labels ───────────────────────────────────────────────
IMPACT_LABELS_FA = {"High": "بالا", "Medium": "متوسط", "Low": "پایین"}
IMPACT_EMOJIS_FA = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# ── layout ───────────────────────────────────────────────────────
PADDING_X = 32
PADDING_Y = 28
ROW_HEIGHT = 56
HEADER_HEIGHT = 60
TITLE_HEIGHT = 72
FOOTER_HEIGHT = 52
MAX_ROWS_PER_IMAGE = 20          # rows per image (Telegram limit ~10000px high ~174 rows)

COL_WIDTHS = {
    "status":   72,
    "impact":   100,
    "country":  105,
    "title":    540,
    "date":     145,
    "time":     100,
}

COL_LABELS = {
    "status":   "وضعیت",
    "impact":   "تاثیر",
    "country":  "کشور",
    "title":    "عنوان رویداد",
    "date":     "تاریخ",
    "time":     "ساعت",
}

COL_ORDER = ["status", "impact", "country", "title", "date", "time"]  # RTL: rightmost=status

# ── Persian digits mapping ───────────────────────────────────────
_EN_DIGITS = "0123456789"
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_TRANS_DIGITS = str.maketrans(_EN_DIGITS, _FA_DIGITS)


def _fa_num(n) -> str:
    """Convert a number to Persian digit string."""
    return str(n).translate(_TRANS_DIGITS)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = VAZIR_BOLD_PATH if bold else VAZIR_REGULAR_PATH
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(MONO_PATH, size)


def _load_mono(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(MONO_PATH, size)
    except OSError:
        return ImageFont.load_default()


def _get_events(db_path: str, cal_tz: str) -> list[dict] | None:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, title_fa, country, event_date, event_time, impact,
                   forecast, previous, url, analysis,
                   alert_pre_sent, alert_15min_sent, alert_30min_sent,
                   result_sent, news_inserted
            FROM forex_events
            ORDER BY event_date, event_time
            """,
        )
        events = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return events
    except Exception as e:
        print(f"[ERROR] Failed to read DB: {e}")
        return None


def _parse_dt(date_str: str, time_str: str, tz: ZoneInfo) -> datetime | None:
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
        return naive.replace(tzinfo=tz)
    except Exception:
        return None


def _format_time_24h(time_str: str) -> str:
    """Convert '10:00am' → '۱۰:۰۰' (24h, Persian digits)."""
    try:
        dt = datetime.strptime(time_str, "%I:%M%p")
        return dt.strftime("%H:%M").translate(_TRANS_DIGITS)
    except Exception:
        return time_str


def _format_date_fa(date_str: str) -> str:
    """Convert '07-23-2026' → '۲۰۲۶/۰۷/۲۳' (YYYY/MM/DD, Persian digits)."""
    try:
        parts = date_str.split("-")
        if len(parts) == 3:
            m, d, y = parts
            return f"{_fa_num(y)}/{_fa_num(m)}/{_fa_num(d)}"
    except Exception:
        pass
    return date_str


def _format_mins_fa(mins: float) -> str:
    """Format remaining minutes in Persian."""
    if abs(mins) < 10000:
        m = int(round(mins))
        if m > 0:
            return f"{_fa_num(m)}+ دقیقه"
        elif m < 0:
            return f"{_fa_num(abs(m))}- دقیقه"
        else:
            return "همین حالا"
    else:
        h = int(round(mins / 60))
        if h > 0:
            return f"{_fa_num(h)}+ ساعت"
        else:
            return f"{_fa_num(abs(h))}- ساعت"


def _impact_color(impact: str) -> tuple[int, int, int]:
    return {
        "High": IMPACT_HIGH,
        "Medium": IMPACT_MEDIUM,
        "Low": IMPACT_LOW,
    }.get(impact, TEXT_SECONDARY)


def _truncate(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if not text:
        return ""
    bbox = font.getbbox(text)
    if bbox[2] - bbox[0] <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.getbbox(text[:mid] + "…")[2] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…" if lo > 0 else "…"


def _render_image(rows: list[dict], output_path: str, page_num: int = 1, total_pages: int = 1) -> str | None:
    """Render a single image from a list of prepared row dicts."""
    if not rows:
        return None

    now_dt = datetime.now().astimezone()

    # ── compute image dimensions ─────────────────────────────────
    total_width = (sum(COL_WIDTHS[c] for c in COL_ORDER)
                   + PADDING_X * 2
                   + len(COL_ORDER) * 2)
    total_height = (PADDING_Y + TITLE_HEIGHT + HEADER_HEIGHT
                    + ROW_HEIGHT * len(rows) + FOOTER_HEIGHT + PADDING_Y)

    # ── create image ─────────────────────────────────────────────
    img = Image.new("RGBA", (total_width, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_title  = _load_font(26, bold=True)
    font_header = _load_font(17, bold=True)
    font_cell   = _load_font(16, bold=False)
    font_footer = _load_font(14, bold=False)
    font_status = _load_font(17, bold=True)

    # ── title (Persian) — right-aligned ──────────────────────────
    page_suffix = f" — بخش {_fa_num(page_num)} از {_fa_num(total_pages)}" if total_pages > 1 else ""
    title_text = f"📊 {_fa_num(len(rows))} رویداد پیش رو — ForexFactory{page_suffix}"
    reshaped_title = _reshape_persian(title_text)
    title_bbox = font_title.getbbox(reshaped_title)
    title_w = title_bbox[2] - title_bbox[0]
    title_x = total_width - PADDING_X - title_w
    draw.text((title_x, PADDING_Y + 16), reshaped_title, fill=ACCENT_VIOLET, font=font_title)

    # ── header row (RTL) ─────────────────────────────────────────
    y = PADDING_Y + TITLE_HEIGHT
    draw.rectangle(
        [(PADDING_X, y), (total_width - PADDING_X, y + HEADER_HEIGHT)],
        fill=HEADER_BG,
    )
    x = total_width - PADDING_X
    for col in COL_ORDER:
        label = COL_LABELS[col]
        reshaped_label = _reshape_persian(label)
        tw = COL_WIDTHS[col]
        x -= tw
        label_bbox = font_header.getbbox(reshaped_label)
        label_w = label_bbox[2] - label_bbox[0]
        # right-align
        draw.text((x + tw - label_w - 4, y + 16), reshaped_label, fill=ACCENT_VIOLET, font=font_header)
        x -= 2

    # ── separator ────────────────────────────────────────────────
    y += HEADER_HEIGHT
    draw.line(
        [(PADDING_X, y), (total_width - PADDING_X, y)],
        fill=BORDER_COLOR, width=1,
    )

    # ── data rows (RTL) ──────────────────────────────────────────
    for i, row in enumerate(rows):
        row_y = y + i * ROW_HEIGHT
        bg = ROW_ODD if i % 2 == 0 else ROW_EVEN
        draw.rectangle(
            [(PADDING_X, row_y), (total_width - PADDING_X, row_y + ROW_HEIGHT)],
            fill=bg,
        )

        x = total_width - PADDING_X
        for col in COL_ORDER:
            val = row[col]
            tw = COL_WIDTHS[col]
            x -= tw

            if col == "status":
                color = SENT_COLOR if val else TEXT_SECONDARY
                draw.text((x + tw//2 - 8, row_y + 14), val or "·", fill=color, font=font_status)
            elif col == "impact":
                orig_impact = {"بالا": "High", "متوسط": "Medium", "پایین": "Low"}.get(val, "")
                reshaped_val = _reshape_persian(val)
                bbox = font_cell.getbbox(reshaped_val)
                text_w = bbox[2] - bbox[0]
                draw.text((x + tw - text_w - 4, row_y + 14), reshaped_val, fill=_impact_color(orig_impact), font=font_cell)
            elif col == "title":
                reshaped_val = _reshape_persian(val)
                truncated = _truncate(reshaped_val, font_cell, tw - 8)
                bbox = font_cell.getbbox(truncated)
                text_w = bbox[2] - bbox[0]
                draw.text((x + tw - text_w - 4, row_y + 14), truncated, fill=TEXT_PRIMARY, font=font_cell)
            else:
                # country, date, time — NOT reshaped (digits/abbreviations, not Persian sentences)
                bbox = font_cell.getbbox(val)
                text_w = bbox[2] - bbox[0]
                draw.text((x + tw - text_w - 4, row_y + 14), val, fill=TEXT_PRIMARY, font=font_cell)

            x -= 2

        # row border
        draw.line(
            [(PADDING_X, row_y + ROW_HEIGHT), (total_width - PADDING_X, row_y + ROW_HEIGHT)],
            fill=BORDER_COLOR, width=1,
        )

    # ── footer (Persian) ─────────────────────────────────────────
    footer_y = y + len(rows) * ROW_HEIGHT + 8
    tehran_now = now_dt.astimezone(TEHRAN_TZ)
    today_str_fa = _format_date_fa(tehran_now.strftime("%m-%d-%Y"))
    footer_text = f"🗓 {today_str_fa}  |  به وقت تهران  |  @ForexEyvazi"
    draw.text((PADDING_X + 12, footer_y), _reshape_persian(footer_text), fill=TEXT_SECONDARY, font=font_footer)

    # ── outer border ─────────────────────────────────────────────
    draw.rectangle(
        [(PADDING_X - 1, PADDING_Y - 1), (total_width - PADDING_X + 1, footer_y + 24)],
        outline=BORDER_COLOR, width=1,
    )

    # ── save ─────────────────────────────────────────────────────
    img.save(output_path, "PNG")
    print(f"[OK] تصویر ذخیره شد → {output_path}  ({total_width}x{total_height})")
    return output_path


def generate_forex_image(
    db_path: str = None,
    output_path: str = None,
    cal_tz: str = None,
) -> str | None:
    """Legacy wrapper — returns the first image path (backward compat)."""
    paths = generate_forex_images(db_path=db_path, output_path=output_path, cal_tz=cal_tz)
    return paths[0] if paths else None


def generate_forex_images(
    db_path: str = None,
    output_path: str = None,
    cal_tz: str = None,
    max_rows: int = MAX_ROWS_PER_IMAGE,
    page_number: int = 0,
) -> list[str]:
    """Generate one or more dark-themed table images of pending ForexFactory events.

    When *page_number* is 0 (default), ALL pages are generated and returned.
    When *page_number* > 0, only that specific page is rendered.
    The header shows "Page X of N" on every page.
    """
    if db_path is None:
        db_path = DB_PATH
    if output_path is None:
        output_path = OUTPUT_PATH
    if cal_tz is None:
        cal_tz = CALENDAR_TIMEZONE

    tz = ZoneInfo(cal_tz)
    events = _get_events(db_path, cal_tz)
    if events is None:
        return []

    # ── filter by impact level (FOREX_ALERT_IMPACTS env var) ──────
    impacts_env = os.getenv("FOREX_ALERT_IMPACTS", "High,Medium,Low")
    allowed_impacts = {x.strip() for x in impacts_env.split(",") if x.strip()}
    if allowed_impacts:
        filtered = [ev for ev in events if ev["impact"] in allowed_impacts]
        skipped = len(events) - len(filtered)
        if skipped:
            print(f"[INFO] Impact filter: kept {len(filtered)} / {len(events)} events (allowed={allowed_impacts})")
        events = filtered

    now_dt = datetime.now().astimezone()

    # ── prepare rows ─────────────────────────────────────────────
    all_rows = []
    for ev in events:
        ev_dt = _parse_dt(ev["event_date"], ev["event_time"], tz)
        if ev_dt is None:
            continue

        ev_tehran = ev_dt.astimezone(TEHRAN_TZ)

        all_rows.append({
            "ev_dt":    ev_dt,
            "status":   "✔" if ev.get("alert_pre_sent") else "",
            "impact":   IMPACT_LABELS_FA.get(ev["impact"], ev["impact"]),
            "country":  ev["country"],
            "title":    ev.get("title_fa") or ev["title"],
            "date":     _format_date_fa(ev_tehran.strftime("%m-%d-%Y")),
            "time":     ev_tehran.strftime("%H:%M").translate(_TRANS_DIGITS),
        })

    if not all_rows:
        print("[INFO] No pending forex events to render.")
        return []

    # ── split into pages ─────────────────────────────────────────
    total_pages = (len(all_rows) + max_rows - 1) // max_rows
    base, ext = os.path.splitext(output_path)

    def _render_page(page: int) -> str | None:
        start = page * max_rows
        end = start + max_rows
        chunk = all_rows[start:end]
        if not chunk:
            return None
        if total_pages > 1:
            page_path = f"{base}_p{page + 1}{ext}"
        else:
            page_path = output_path
        return _render_image(chunk, page_path, page_num=page + 1, total_pages=total_pages)

    if page_number > 0:
        idx = page_number - 1
        if idx < 0 or idx >= total_pages:
            print(f"[WARN] Page {page_number} requested but only {total_pages} pages exist.")
            return []
        result = _render_page(idx)
        return [result] if result else []
    else:
        paths = []
        for page in range(total_pages):
            result = _render_page(page)
            if result:
                paths.append(result)
        return paths


if __name__ == "__main__":
    result = generate_forex_image()
    if result:
        print(f"\n✅ انجام شد! مسیر: {result}")
    else:
        print("\n❌ تصویری تولید نشد (رویدادی موجود نیست یا خطا در پایگاه داده).")
