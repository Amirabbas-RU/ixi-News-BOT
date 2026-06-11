import requests
import xml.etree.ElementTree as ET
from sources_base import BaseRSSSource
from rss_utils import fetch_og_image
import config


class ForexFactoryCalendar(BaseRSSSource):
    name = "ForexFactory"
    rss_url = config.FOREXFACTORY_CALENDAR_URL

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(self.rss_url, timeout=15, headers=headers)
        resp.raise_for_status()
        raw = resp.content.decode("windows-1252", errors="replace")
        root = ET.fromstring(raw)

        all_events = root.findall("event")

        news_items = []
        for event in all_events:
            title = event.findtext("title", "")
            country = event.findtext("country", "")
            date_str = event.findtext("date", "")
            time_str = event.findtext("time", "")
            impact = event.findtext("impact", "")
            forecast = event.findtext("forecast", "") or ""
            previous = event.findtext("previous", "") or ""
            url = event.findtext("url", "")

            published = f"{date_str} {time_str}".strip()
            content = self._build_content(title, country, impact, forecast, previous)
            image_url = fetch_og_image(url) if url and impact == "High" else None

            news_items.append({
                "title": title,
                "url": url,
                "image_url": image_url,
                "source": self.name,
                "published_at": published,
                "content": content,
            }
            )

        return news_items

    @staticmethod
    def _build_content(
        title: str, country: str, impact: str, forecast: str, previous: str
    ) -> str:
        parts = [f"[{country}] {title} — Impact: {impact}."]

        if forecast or previous:
            parts.append(
                f"Market Forecast: {forecast or 'N/A'}, Previous: {previous or 'N/A'}."
            )

        return " ".join(parts)
