import re
import requests
from bs4 import BeautifulSoup


def fetch_og_image(url: str) -> str | None:
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image["content"]
    except Exception as e:
        print("ERROR fetching OG image:", e)

    return None


def extract_image_url(entry):
    # 1. CNBC: image in links (enclosure)
    if hasattr(entry, "links"):
        for link in entry.links:
            if (
                link.get("rel") == "enclosure"
                and link.get("type", "").startswith("image")
            ):
                return link.get("href")

    # 2. media:content (Reuters, some feeds)
    if entry.get("media_content"):
        for media in entry.get("media_content"):
            url = media.get("url")
            if url:
                return url

    # 3. media:thumbnail (Yahoo)
    if entry.get("media_thumbnail"):
        for thumb in entry.get("media_thumbnail"):
            url = thumb.get("url")
            if url:
                return url

    # 4. img inside summary (last fallback)
    if entry.get("summary"):
        match = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            entry.summary
        )
        if match:
            return match.group(1)

    return None



def extract_investing_article_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        article = soup.find("div", class_="WYSIWYG articlePage")
        if not article:
            return ""

        paragraphs = article.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)

        return text

    except Exception as e:
        return ""
    

def extract_investing_image(url: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        selectors = [
            "img.js-article-image",
            "article img",
            ".articlePage img",
            "img[src*='investing.com']",
            "meta[property='og:image']"
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                src = element.get("src") or element.get("content")
                if src:
                    # بررسی URL کامل بودن
                    if src.startswith("http"):
                        return src
                    elif src.startswith("//"):
                        return f"https:{src}"
                    else:
                        return f"https://www.investing.com{src}" if src.startswith("/") else src
        return None
    except Exception:
        return None
