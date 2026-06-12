

#---------------------------------<< global variables >>---------------------------------
HIGH_IMPACT_KEYWORDS = {
    "Fed": 5,
    "Interest Rate": 5,
    "Inflation": 4,
    "CPI": 5,
    "War": 5,
    "Sanctions": 4,
    "Oil": 3,
    "Bitcoin": 4,
    "Crypto": 4,
    "ECB": 4,
    "Bank": 3,
    "Stock Market": 3,
    "NASDAQ": 3,
    "S&P 500": 3,
    "Market": 2,
    "Economy": 2,
    "Trade": 2,
    "Currency": 2,
    "Gold": 2,
    "Bond": 2,
    "USD": 2,
    "Euro": 2,
}

SOURCE_SCORE = {
    "Reuters": 4,
    "CNBC": 4,
    "Investing.com": 4,
}


#---------------------------------<< calculate news score >>---------------------------------
def calculate_keyword_score(text: str) -> int:
    score = 0
    text_lower = text.lower()
    for keyword, value in HIGH_IMPACT_KEYWORDS.items():
        if keyword.lower() in text_lower:
            score += value
    return score

def calculate_total_score(news_item: dict) -> float:
    """
    news_item: دیکشنری شامل title, content, source
    خروجی: امتیاز عددی بین 0 تا بی‌نهایت
    """
    score = calculate_keyword_score(news_item["title"])
    score += calculate_keyword_score(news_item.get("content", ""))
    score += SOURCE_SCORE.get(news_item["source"], 0)
    return score
