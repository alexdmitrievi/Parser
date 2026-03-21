"""tektorg.ru — заглушка/минимальный парсер (223-ФЗ)."""

from __future__ import annotations

from typing import Any

from scrapers.base import BaseScraper


class TektorgScraper(BaseScraper):
    source_platform = "tektorg"
    law_type = "223-fz"

    def listing_url(self) -> str:
        return "https://www.tektorg.ru/"

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        # Разметка сайта может меняться — при необходимости доработать селекторы.
        return []
