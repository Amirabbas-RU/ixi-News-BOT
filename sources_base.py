from abc import ABC, abstractmethod

class BaseRSSSource(ABC):
    name: str
    rss_url: str

    @abstractmethod
    def fetch(self) -> list[dict]:
        """
        خروجی: لیستی از دیکشنری‌های نرمال‌شده خبر
        """
        pass
