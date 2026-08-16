import re
import unicodedata

from logger import logger
from openai import OpenAI
import config


# ایجاد کلاینت OpenRouter
client = OpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url=config.OPENROUTER_BASE_URL,
    timeout=30
)


title_cache: dict[str, str] = {}


def _attempt_models(primary: str) -> list[str]:
    """Per-attempt model chain: 3x primary, then 2x spare (when configured).

    The spare model (OPENROUTER_SPARE_MODEL) only runs AFTER the primary has
    failed its full retry budget — success paths never touch it.
    """
    chain = [primary]
    spare = (getattr(config, "OPENROUTER_SPARE_MODEL", None) or "").strip()
    if spare and spare not in chain:
        chain.append(spare)
    return [m for m, n in zip(chain, (3, 2)) for _ in range(n)]


def translate_title_fa(title: str) -> str | None:
    if title in title_cache:
        return title_cache[title]

    # Persistent Farsi translation DB — avoid re-translating the same title
    # every cycle / after restart.
    cached_fa = _get_translation(title)
    if cached_fa:
        title_cache[title] = cached_fa
        return cached_fa

    prompt = f"فقط عنوان را به فارسی روان ترجمه کن و هیچ چیز دیگر:\n\n{title}"

    # Retry transient OpenRouter failures (timeout / rate limit) so caption
    # generation doesn't fall back to raw English titles. If the primary
    # model exhausts its retries, fall back to OPENROUTER_SPARE_MODEL.
    models = _attempt_models(config.OPENROUTER_MODEL)
    for attempt, model in enumerate(models):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "فقط عنوان را به فارسی ترجمه کن و هیچ چیز دیگر ننویس."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            text = response.choices[0].message.content
            if text and text.strip():
                clean = text.strip()
                for prefix in ["عنوان خبر به فارسی روان و دقیق:", "عنوان خبر:", "عنوان به فارسی:"]:
                    if clean.startswith(prefix):
                        clean = clean[len(prefix):].strip()
                title_cache[title] = clean
                _save_translation(title, clean)
                return clean
        except Exception as e:
            logger.error(f"Title translation error ({model}, attempt {attempt + 1}/{len(models)}): {e}")
        if attempt < len(models) - 1:
            import time as _time
            _time.sleep(2 * (attempt + 1))
    return None


def _get_translation(en: str) -> str | None:
    try:
        from translation_store import get_translation
        return get_translation(en)
    except Exception as e:
        logger.error(f"translation store read error: {e}")
        return None


def _save_translation(en: str, fa: str):
    try:
        from translation_store import save_translation
        save_translation(en, fa)
    except Exception as e:
        logger.error(f"translation store write error: {e}")


def _safe_truncate(text: str, max_chars: int) -> str:
    """Cut text at the last word boundary before max_chars — never mid-word."""
    if not text or len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Back up to the last whitespace so we don't split a word
    idx = cut.rfind(" ")
    if idx > max_chars * 0.6:
        cut = cut[:idx]
    return cut.rstrip() + "…"


def summarize_news_fa(title: str, content: str) -> dict:
    """
    خروجی:
    {
        "title_fa": "...",
        "summary_fa": "..."
    }
    """
    prompt = f"""
        شما یک تحلیلگر حرفه‌ای اخبار مالی هستید.

        وظایف:
        1. عنوان خبر زیر را به فارسی روان، دقیق و خبری ترجمه کن
        2. متن خبر را به فارسی حداکثر در ۲ پاراگراف کوتاه خلاصه کن
        3. در انتها بر اساس تحلیل خودت، تاثیر مورد انتظار این خبر بر بازارهای مالی را خیلی کوتاه در یک خط بنویس

        قوانین مهم:
        - تعداد کل کاراکترها (شامل کاراکترهای عنوان خبر و متن خبر و تحلیل انتهایی خبر) نباید از 950 کاراکتر بیشتر شود
        - لحن کاملاً خبری و حرفه‌ای باشد
        - تمرکز بر اثر خبر بر بازارهای مالی باشد
        - از اغراق، پیش‌بینی شخصی و جملات کلی پرهیز کن
        - از عباراتی مانند «در این خبر»، «این گزارش» استفاده نکن
        - خروجی فقط متن ساده باشد (بدون markdown)

        فرمت خروجی دقیقاً به این شکل باشد:

        عنوان فارسی:
        <📌 عنوان خبر به فارسی>

        خلاصه فارسی:
        <خلاصه خبر به فارسی>

        تاثیر در بازارهای مالی: 
        <🔷 تاثیر مورد انتظار خبر بر بازارهای مالی>

        عنوان خبر:
        {title}

        متن خبر:
        {content[:3500]}
    """

    # Retry transient OpenRouter failures / empty responses so a single hiccup
    # doesn't drop the news from the channel. Falls back to the spare model
    # after the primary exhausts its retries.
    models = _attempt_models(config.OPENROUTER_MODEL)
    for attempt, model in enumerate(models):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "شما یک تحلیلگر حرفه‌ای اخبار مالی هستید."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1500
            )

            text = response.choices[0].message.content
            if not text or not text.strip():
                logger.error(f"OpenAI returned empty response ({model}, attempt {attempt + 1}/{len(models)})")
            elif "عنوان فارسی:" not in text or "خلاصه فارسی:" not in text:
                logger.error(f"OpenAI returned invalid format ({model}, attempt {attempt + 1}/{len(models)})")
            else:
                title_fa = text.split("عنوان فارسی:")[1].split("خلاصه فارسی:")[0].strip()
                summary_fa = text.split("خلاصه فارسی:")[1].strip()

                if not title_fa or not summary_fa:
                    logger.error(f"OpenAI returned empty title or summary ({model}, attempt {attempt + 1}/{len(models)})")
                else:
                    # Defensive: never let a truncated Persian word reach the channel
                    summary_fa = _safe_truncate(summary_fa, 950)
                    return {
                        "title_fa": title_fa,
                        "summary_fa": summary_fa
                    }
        except Exception as e:
            logger.error(f"OpenRouter summarization error ({model}, attempt {attempt + 1}/{len(models)}): {e}")
        if attempt < len(models) - 1:
            import time as _time
            _time.sleep(2 * (attempt + 1))
    return None


#---------------------------------<< forex event analyzer >>---------------------------------
def summarize_forex_event_fa(event: dict) -> str:
    prompt = f"""
    شما یک تحلیلگر حرفه‌ای بازارهای مالی هستید.

    یک رویداد اقتصادی پیش رو داریم:

    عنوان: {event['title']}
    کشور/ارز: {event['country']}
    میزان تاثیر: {event['impact']}
    پیش‌بینی: {event.get('forecast', 'نامشخص')}
    مقدار قبلی: {event.get('previous', 'نامشخص')}

    لطفاً یک تحلیل کوتاه و حرفه‌ای به فارسی ارائه بده:
    ۱. توضیح دهید این رویداد چیست و چرا مهم است
    ۲. پیش‌بینی بازار نسبت به مقدار قبلی چه پیامی دارد
    ۳. تاثیر مورد انتظار بر بازارهای مالی را تحلیل کنید

    قوانین:
    - حداکثر ۴۰۰ کاراکتر
    - لحن کاملاً خبری و حرفه‌ای
    - از اغراق و پیش‌بینی شخصی پرهیز کن
    - خروجی فقط متن ساده (بدون مارک داون)
    """

    # Retry transient failures so we get a real Persian analysis instead of
    # falling back to the plain English template. Spare model kicks in after
    # the primary exhausts its retries.
    models = _attempt_models(config.OPENROUTER_MODEL)
    for attempt, model in enumerate(models):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "شما یک تحلیلگر حرفه‌ای بازارهای مالی هستید."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=700
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("Empty response")
            return _safe_truncate(content.strip(), 400)
        except Exception as e:
            logger.error(f"Forex event analysis error ({model}, attempt {attempt + 1}/{len(models)}): {e}")
            if attempt < len(models) - 1:
                import time as _time
                _time.sleep(2 * (attempt + 1))
    impact_map = {"High": "پرنفوذ", "Medium": "متوسط", "Low": "کم"}
    impact_fa = impact_map.get(event.get("impact", ""), "")
    return (
        f"⚠️ رویداد اقتصادی: {event['title']} | "
        f"کشور: {event['country']} | "
        f"تاثیر: {impact_fa} | "
        f"پیش‌بینی: {event.get('forecast', 'نامشخص')} | "
        f"قبلی: {event.get('previous', 'نامشخص')}"
    )


# ── Daily Calendar Caption Generator ───────────────────────────────────────────

COUNTRY_FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿", "CNY": "🇨🇳",
}
COUNTRY_FA = {
    "USD": "ایالات متحده", "EUR": "منطقه یورو", "GBP": "بریتانیا",
    "JPY": "ژاپن", "AUD": "استرالیا", "CAD": "کانادا",
    "CHF": "سوئیس", "NZD": "نیوزیلند", "CNY": "چین",
}
IMPACT_EMOJI = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}

_caption_cache: dict[str, str] = {}


def _norm_persian(s: str) -> str:
    """Normalize Persian text for loose title matching: drop zero-width
    characters (zwnj/zwj/rtl), NFKC-fold, strip punctuation, collapse spaces."""
    if not s:
        return ""
    s = s.replace("\u200c", "").replace("\u200f", "").replace("\ufeff", "").replace("\u200d", "")
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[،.;:!؟?()\[\]\"'\-_|/]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _caption_covers_title(result: str, title: str) -> bool:
    """True when the model's caption already covers this event's title.

    Exact match wins; otherwise one-directional substring containment on the
    normalized text (min length 8 chars) — so a model that paraphrased
    ('بیانیه سیاست پولی' vs DB 'بیانیه سیاست پولی بانک مرکزی استرالیا') is
    treated as covered. Appending it anyway would duplicate the block, which is
    exactly the 'repeated event' trash seen on the channel."""
    t_norm = _norm_persian(title)
    if not t_norm:
        return False
    if t_norm in _norm_persian(result):
        return True
    for line in result.split("\n"):
        l_norm = _norm_persian(line)
        # only compare real titles — strip the 📣/🚦 block header if present
        if "|" in line:
            l_norm = _norm_persian(line.split("|", 1)[1])
        if len(l_norm) >= 8 and len(t_norm) >= 8 and (l_norm in t_norm or t_norm in l_norm):
            return True
    return False


def generate_daily_calendar_caption(
    events: list[dict],
    date_header: str,
    channel_name: str = "@ForexEyvazi",
) -> str | None:
    """Generate a rich Persian daily economic calendar analysis using OpenRouter."""
    if not events:
        return None

    # ── Build event context (🔴 High + 🟡 Medium ONLY — skip 🟢 Low) ────
    important_events = [ev for ev in events if ev.get("impact") in ("High", "Medium")]
    if not important_events:
        return None

    # Dynamic cache key: date + fingerprint of the ACTUAL important events.
    # If the calendar fills in / changes during the day, the key changes and
    # a fresh caption is generated — never reuse a stale morning caption.
    fingerprint_parts = []
    for ev in important_events:
        fingerprint_parts.append(
            f"{ev.get('id')}|{ev.get('title')}|{ev.get('event_time')}|{ev.get('impact')}"
        )
    fingerprint_parts.sort()
    cache_key = f"{date_header}::{hash(tuple(fingerprint_parts))}"
    if cache_key in _caption_cache:
        logger.info(f"Calendar caption cache hit ({len(important_events)} events)")
        return _caption_cache[cache_key]
    if any(k.startswith(date_header + "::") for k in list(_caption_cache)):
        logger.info("Event set changed — invalidating old date-cached caption")
        for old_key in [k for k in list(_caption_cache) if k.startswith(date_header + "::")]:
            del _caption_cache[old_key]

    event_blocks = []
    for ev in important_events:
        flag = COUNTRY_FLAG.get(ev.get("country", ""), "")
        country_fa = COUNTRY_FA.get(ev.get("country", ""), ev.get("country", ""))
        impact_emoji = IMPACT_EMOJI.get(ev.get("impact", ""), "")
        title_fa = ev.get("title_fa")
        if not title_fa:
            title_fa = translate_title_fa(ev.get("title", ""))
            if title_fa:
                ev["title_fa"] = title_fa
        if not title_fa:
            title_fa = ev.get("title", "")
        time_str = ev.get("event_time", "")

        parts = [
            f"📣 {country_fa} | {ev.get('country', '')} {flag}",
            f"{impact_emoji} {time_str} | {title_fa}",
        ]
        if ev.get("forecast"):
            parts.append(f"   پیش‌بینی: {ev['forecast']}")
        if ev.get("previous"):
            parts.append(f"   مقدار قبلی: {ev['previous']}")
        event_blocks.append("\n".join(parts))

    events_text = "\n\n".join(event_blocks)

    prompt = f"""شما یک تحلیلگر بازارهای مالی هستید. تحلیل امروز را به فارسی برای کپشن تلگرام بنویس.

{date_header}

رویدادهای مهم امروز (دقیقاً {len(important_events)} مورد — همه باید پوشش داده شوند):

{events_text}

🎯 قالب خروجی:

🎯 تمرکز بازار:
[۲-۳ خط]

✅ رویدادهای مهم:

📣 سوئیس | CHF 🇨🇭
🟡 10:00 | CPI m/m
🔹 تحلیل دقیقاً ۲ خط (مثال)

📣 آمریکا | USD 🇺🇸
🔴 17:30 | ISM Manufacturing PMI
🔹 تحلیل دقیقاً ۳ خط (مثال)

(برای همه {len(important_events)} رویداد تکرار کن — هر رویداد فقط یک 🔹)

🧭 هشدار:
[۱ خط]

🚨 قوانین:
- ⚠️ مهم‌ترین قانون: کل متن نهایی حداکثر ۸۵۰ کاراکتر باشد — اگر بیشتر شد، کوتاه‌تر بنویس
- هر خط تحلیل حداکثر ۵۵ کاراکتر (یک جمله کوتاه)
- هر رویداد: فقط یک 🔹 و حداکثر ۲ خط تحلیل کوتاه و دقیق — بیش از ۲ خط ممنوع
- هر رویداد را دقیقاً یک بار ذکر کن — هیچ رویدادی تکراری نباشد
- 🔴: ۲ خط کوتاه. 🟡: ۱-۲ خط کوتاه
- همه {len(important_events)} رویداد — یکی کم نشود
- تمرکز بازار: حداکثر ۲ خط کوتاه. هشدار: فقط ۱ خط کوتاه
- بدون توضیح اضافی. فقط متن ساده فارسی"""

    calendar_model = getattr(config, "OPENROUTER_CALENDAR_MODEL", None) or "deepseek/deepseek-chat"
    # Try the primary calendar model, then fall back to OPENROUTER_SPARE_MODEL
    # if it exhausts its attempts. Previously this was a single shot — one
    # transient failure dropped the whole caption to the plain date line.
    models = _attempt_models(calendar_model)
    result = None
    for attempt, model in enumerate(models):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "شما یک تحلیلگر حرفه‌ای بازارهای مالی هستید. خروجی فقط متن ساده فارسی."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=max(2000, len(important_events) * 280 + 1000),
            )
            text = response.choices[0].message.content
            if not text or not text.strip():
                logger.error(f"OpenRouter returned empty calendar caption ({model}, attempt {attempt + 1}/{len(models)})")
            elif len(text.strip()) < 50:
                logger.warning(f"Calendar caption too short ({len(text.strip())} chars) from {model}, discarding: {text.strip()[:80]}...")
            else:
                result = text.strip()
                break
        except Exception as e:
            logger.error(f"Calendar caption generation error ({model}, attempt {attempt + 1}/{len(models)}): {e}")
        if attempt < len(models) - 1:
            import time as _time
            _time.sleep(2 * (attempt + 1))

    if result is None:
        return None

    # Guarantee EVERY important event appears in the caption. The model can
    # stop early or omit a title, so deterministically append anything the
    # model skipped — built from the real DB fields we already have.
    covered = set()
    for ev in important_events:
        t = (ev.get("title_fa") or ev.get("title", "")).strip()
        if t and _caption_covers_title(result, t):
            covered.add(ev.get("id"))

    missing_blocks = []
    for ev in important_events:
        if ev.get("id") in covered:
            continue
        flag = COUNTRY_FLAG.get(ev.get("country", ""), "")
        country_fa = COUNTRY_FA.get(ev.get("country", ""), ev.get("country", ""))
        impact_emoji = IMPACT_EMOJI.get(ev.get("impact", ""), "")
        title = (ev.get("title_fa") or ev.get("title", "") or "").strip()
        block = (
            f"📣 {country_fa} | {ev.get('country', '')} {flag}\n"
            f"{impact_emoji} {ev.get('event_time', '')} | {title}"
        )
        if ev.get("forecast"):
            block += f"\n   پیش‌بینی: {ev['forecast']}"
        if ev.get("previous"):
            block += f"\n   مقدار قبلی: {ev['previous']}"
        missing_blocks.append(block)

    if missing_blocks:
        result += "\n\n" + "\n\n".join(missing_blocks)
        logger.warning(
            f"Appended {len(missing_blocks)} event(s) the model omitted "
            f"({len(covered)}/{len(important_events)} covered)"
        )

    _caption_cache[cache_key] = result
    logger.info(f"Calendar caption generated ({len(result)} chars, {len(covered) + len(missing_blocks)}/{len(important_events)} events)")
    return result
