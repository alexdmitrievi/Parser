"""Парсер Сбербанк-АСТ (sberbank-ast.ru).

Федеральная ЭТП — одна из крупнейших по 44-ФЗ и 223-ФЗ.
Поиск через HTTP (HTML-парсинг).
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


class SberbankAstScraper(BaseScraper):
    """Парсер sberbank-ast.ru."""

    platform = "sberbank_ast"
    base_url = "https://www.sberbank-ast.ru"
    min_delay = 4.0
    max_delay = 8.0

    SEARCH_URL = "https://www.sberbank-ast.ru/purchaseList.aspx"

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y"]:
            try:
                return datetime.strptime(s.strip()[:16], fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        blocks = soup.select(
            ".resultBlock, .purchase-item, .tender-row, "
            "tr.resultRow, .search-result-item"
        )

        for block in blocks:
            item = {}

            link = block.select_one("a[href*='Purchase'], a.purchase-link, h3 a, a.tender-link")
            if link:
                item["title"] = link.get_text(strip=True)
                href = link.get("href", "")
                item["url"] = self.base_url + href if href.startswith("/") else href
                num_match = re.search(r"(\d{10,})", link.get_text() + href)
                if num_match:
                    item["registry_number"] = num_match.group(1)

            if not item.get("title"):
                continue

            price_el = block.select_one(".price, .sum, .nmck, td:nth-child(3)")
            if price_el:
                cleaned = re.sub(r"[^\d.]", "", price_el.get_text().replace(",", ".").replace(" ", ""))
                try:
                    item["nmck"] = float(cleaned)
                except ValueError:
                    pass

            customer_el = block.select_one(".customer, .organizer")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)

            date_el = block.select_one(".date-end, .deadline, .endDate")
            if date_el:
                item["deadline"] = date_el.get_text(strip=True)

            results.append(item)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        return [
            TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="44-fz",
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
                logger.info(f"[Sberbank-AST] Searching: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        url = f"{self.SEARCH_URL}?{urlencode({'searchString': query, 'page': str(page)})}"
                        resp = self.fetch(url)
                        items = self._parse_page(resp.text)
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[Sberbank-AST] Total: {len(all_tenders)} tenders")
        return all_tenders
