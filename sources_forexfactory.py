
import json, os, xml.etree.ElementTree as ET
import requests
import config
from logger import logger

CACHE_PATH = os.path.join(os.path.dirname(__file__), "forex_cache.json")


class ForexFactoryCalendar:
    name = "ForexFactory"
    rss_url = config.FOREXFACTORY_CALENDAR_URL

    def _read_cache(self) -> list[dict] | None:
        try:
            if os.path.exists(CACHE_PATH):
                with open(CACHE_PATH) as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _write_cache(self, events: list[dict]):
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(events, f)
        except Exception as e:
            logger.warning(f"ForexFactory cache write error: {e}")

    def _is_rate_limited(self, text: str) -> bool:
        return "Rate Limited" in text or "Request Denied" in text or "429" in text[:200]

    def fetch(self) -> list[dict]:
        try:
            resp = requests.get(
                self.rss_url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ForexFactoryBot/1.0)"},
            )
            if self._is_rate_limited(resp.text):
                logger.warning("ForexFactory rate limited — using cache")
                cached = self._read_cache()
                if cached:
                    logger.info(f"ForexFactory: {len(cached)} events from cache")
                    return cached
                logger.error("ForexFactory: rate limited and no cache available")
                return []

            resp.encoding = "windows-1252"
            root = ET.fromstring(resp.text)
            events = []
            for event_elem in root.findall("event"):
                event = {
                    "title": event_elem.findtext("title", ""),
                    "country": event_elem.findtext("country", ""),
                    "date": event_elem.findtext("date", ""),
                    "time": event_elem.findtext("time", ""),
                    "impact": event_elem.findtext("impact", ""),
                    "forecast": event_elem.findtext("forecast") or "",
                    "previous": event_elem.findtext("previous") or "",
                    "url": event_elem.findtext("url", ""),
                }
                events.append(event)
            self._write_cache(events)
            logger.info(f"ForexFactory: {len(events)} events fetched")
            return events
        except Exception as e:
            logger.error(f"ForexFactory fetch error: {e}")
            cached = self._read_cache()
            if cached:
                logger.info(f"ForexFactory: {len(cached)} events from cache (after error)")
                return cached
            return []
