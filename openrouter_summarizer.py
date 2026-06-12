from logger import logger
from openai import OpenAI
import config 


# ایجاد کلاینت OpenRouter
client = OpenAI(
    api_key = config.OPENROUTER_API_KEY,
    base_url = config.OPENROUTER_BASE_URL
)

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
        2. متن خبر را به فارسی حداکثر در ۳ پاراگراف کوتاه خلاصه کن
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

    try:
        response = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "شما یک تحلیلگر حرفه‌ای اخبار مالی هستید."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=350
        )

        text = response.choices[0].message.content
        
        if "عنوان فارسی:" not in text or "خلاصه فارسی:" not in text:
            logger.error("OpenAI returned invalid format")
            return None

        title_fa = text.split("عنوان فارسی:")[1].split("خلاصه فارسی:")[0].strip()
        summary_fa = text.split("خلاصه فارسی:")[1].strip()

        if not title_fa or not summary_fa:
            logger.error("OpenAI returned empty title or summary")
            return None

        return {
            "title_fa": title_fa,
            "summary_fa": summary_fa
        }

    except Exception as e:
        logger.error(f"OpenRouter summarization error: {e}")
        return {
            "title_fa": f"خطا در ترجمه: {title[:50]}...",
            "summary_fa": "متأسفانه خلاصه‌سازی با خطا مواجه شد. لطفاً به لینک اصلی خبر مراجعه کنید."
        }


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

    try:
        response = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "شما یک تحلیلگر حرفه‌ای بازارهای مالی هستید."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response")
        text = content.strip()
        if not text:
            raise ValueError("Empty response")
        return text
    except Exception as e:
        logger.error(f"Forex event analysis error: {e}")
        impact_map = {"High": "پر影响", "Medium": "متوسط", "Low": "کم"}
        impact_fa = impact_map.get(event.get("impact", ""), "")
        return (
            f"⚠️ رویداد اقتصادی: {event['title']} | "
            f"کشور: {event['country']} | "
            f"تاثیر: {impact_fa} | "
            f"پیش‌بینی: {event.get('forecast', 'نامشخص')} | "
            f"قبلی: {event.get('previous', 'نامشخص')}"
        )

