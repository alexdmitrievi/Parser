"""Базовый класс парсеров тендеров."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


class BaseScraper(ABC):
    """Все парсеры реализуют parse_tenders() и run()."""

    source_platform: str = "unknown"
    law_type: str = "commercial"
    timeout: int = 45

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str) -> str | None:
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:
            logger.warning("fetch failed %s: %s", url, e)
            return None

    @abstractmethod
    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        """Извлечь список сырых тендеров из HTML/ответа."""

    def run(self) -> list[dict[str, Any]]:
        """Точка входа: загрузить страницу поиска и вернуть тендеры."""
        url = self.listing_url()
        if not url:
            return []
        html = self.fetch(url)
        if not html:
            return []
        raw = self.parse_tenders(html)
        out: list[dict[str, Any]] = []
        for item in raw:
            item.setdefault("source_platform", self.source_platform)
            item.setdefault("law_type", self.law_type)
            out.append(item)
        return out

    def listing_url(self) -> str:
        """URL страницы списка (переопределяется в подклассах)."""
        return ""

    def _clean(self, s: str | None) -> str | None:
        if s is None:
            return None
        t = " ".join(str(s).split())
        return t or None
