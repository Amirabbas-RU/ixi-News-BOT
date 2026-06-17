import config
import feedparser
import requests
from sources_base import BaseRSSSource
from rss_utils import extract_image_url, fetch_og_image

class CNBCRSS(BaseRSSSource):
    name = "CNBC"
    rss_url = config.CNBC_RSS_URL

    REQUEST_TIMEOUT = 15

    def fetch(self) -> list[dict]:
        if not self.rss_url:
            return []
        try:
            resp = requests.get(
                self.rss_url,
                timeout=self.REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except requests.RequestException as e:
            print(f"[CNBC] Failed to fetch RSS: {e}")
            return []

        news_items = []

        print(f"[CNBC] feed entries found: {len(feed.entries)}")

        for entry in feed.entries:
            image_url = extract_image_url(entry)

            if not image_url:
                image_url = fetch_og_image(entry.get("link"))

            news_items.append({
                "title": entry.get("title"),
                "url": entry.get("link"),
                "image_url": image_url,
                "source": self.name,
                "published_at": entry.get("published"),
                "content": entry.get("summary", "")
            })

        return news_items
