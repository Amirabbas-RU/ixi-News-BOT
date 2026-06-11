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
        - تعداد کل کاراکترها (شامل کاراکترهای عنوان خبر و متن خبر و تحلیل انتهایی خبر) نباید از 1800 کاراکتر بیشتر شود
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
            max_tokens=800
        )

        text = response.choices[0].message.content

        if not text:
            logger.error("OpenRouter returned empty content")
            return None

        if "عنوان فارسی:" not in text or "خلاصه فارسی:" not in text:
            logger.error("OpenAI returned invalid format")
            return None

        title_fa = text.split("عنوان فارسی:")[1].split("خلاصه فارسی:")[0].strip()
        summary_fa = text.split("خلاصه فارسی:")[1].strip()
        if "تاثیر در بازارهای مالی" in summary_fa:
            summary_fa = summary_fa.split("تاثیر در بازارهای مالی")[0].strip()

        if not title_fa or not summary_fa:
            logger.error("OpenAI returned empty title or summary")
            return None

        return {
            "title_fa": title_fa,
            "summary_fa": summary_fa
        }

    except Exception as e:
        err_str = str(e)
        if "429" not in err_str:
            logger.error(f"OpenRouter summarization error: {e}")
        return None

