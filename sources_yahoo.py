import config
import feedparser
from sources_base import BaseRSSSource
from rss_utils import extract_image_url

class YahooRSS(BaseRSSSource):
    name = "Yahoo"
    rss_url = config.YAHOO_RSS_URL

    def fetch(self) -> list[dict]:
        feed = feedparser.parse(self.rss_url)
        news_items = []
        

        for entry in feed.entries:
            image_url = extract_image_url(entry)

            news_items.append({
                "title": entry.get("title"),
                "url": entry.get("link"),
                "image_url": image_url,
                "source": self.name, 
                "published_at": entry.get("published"),
                "content": entry.get("summary") or entry.get("title")
            })

        return news_items
