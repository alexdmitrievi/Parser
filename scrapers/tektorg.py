"""Парсер ТЭК-Торг (tektorg.ru).

Федеральная ЭТП. Специализация: энергетика, ЖКХ, но также
строительство и поставки.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class TekTorgScraper(BaseScraper):
    """Парсер tektorg.ru."""

    platform = "tektorg"
    base_url = "https://www.tektorg.ru"
    min_delay = 3.0
    max_delay = 7.0

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y"]:
            try:
                return datetime.strptime(s.strip()[:16], fmt)
            except ValueError:
                continue
        return None

    def _search_page(self, query: str, page: int = 1) -> list[dict]:
        url = f"{self.base_url}/procedures?{urlencode({'search': query, 'page': str(page)})}"
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        blocks = soup.select(".procedure-item, .tender-card, .search-result-item, article, tr.row")

        for block in blocks:
            item = {}
            link = block.select_one("a.title, h3 a, a[href*='procedure']")
            if link:
                item["title"] = link.get_text(strip=True)
                href = link.get("href", "")
                item["url"] = self.base_url + href if href.startswith("/") else href
                num_match = re.search(r"(\d{8,})", href + link.get_text())
                if num_match:
                    item["registry_number"] = num_match.group(1)

            if not item.get("title"):
                continue

            price_el = block.select_one(".price, .sum, .nmck")
            if price_el:
                cleaned = re.sub(r"[^\d.]", "", price_el.get_text().replace(",", ".").replace(" ", ""))
                try:
                    item["nmck"] = float(cleaned)
                except ValueError:
                    pass

            customer_el = block.select_one(".customer, .organizer")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)

            date_el = block.select_one(".deadline, .end-date")
            if date_el:
                item["deadline"] = date_el.get_text(strip=True)

            results.append(item)
        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        return [
            TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="223-fz",
                title=item["title"],
                customer_name=item.get("customer"),
                nmck=item.get("nmck"),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            )
            for item in raw_items if item.get("title")
        ]

    def run(self, queries: list[str] | None = None, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = ["мебель", "подряд", "ремонт", "строительство"]

        all_tenders: list[TenderCreate] = []
        with self:
            for query in queries:
                logger.info(f"[TekTorg] Searching: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        items = self._search_page(query, page)
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)}")
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[TekTorg] Total: {len(all_tenders)}")
        return all_tenders
