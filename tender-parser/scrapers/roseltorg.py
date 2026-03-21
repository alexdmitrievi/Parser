"""Парсер Росэлторг (roseltorg.ru).

Одна из 8 федеральных ЭТП. Крупнейшая по объёму 44-ФЗ.
Поиск через REST API (JSON).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RoseltorgScraper(BaseScraper):
    """Парсер roseltorg.ru через поисковый API."""

    platform = "roseltorg"
    base_url = "https://www.roseltorg.ru"
    min_delay = 3.0
    max_delay = 6.0

    SEARCH_API = "https://www.roseltorg.ru/api/search"

    def _search(self, query: str, page: int = 1, per_page: int = 50) -> dict:
        """Выполнить поиск через API Росэлторга."""
        params = {
            "query": query,
            "page": page,
            "per_page": per_page,
            "sort": "relevance",
            "status": "accepting",
        }
        try:
            resp = self.fetch(self.SEARCH_API, params=params)
            return resp.json()
        except Exception:
            # Fallback на HTML-парсинг
            return self._search_html(query, page)

    def _search_html(self, query: str, page: int = 1) -> dict:
        """Fallback: парсинг HTML страницы поиска."""
        from bs4 import BeautifulSoup
        from urllib.parse import urlencode

        url = f"{self.base_url}/procedures/search?{urlencode({'query': query, 'page': str(page)})}"
        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        blocks = soup.select(".search-results__item, .procedure-item, .tender-card")
        for block in blocks:
            item = {}
            title_el = block.select_one("a.procedure-title, h3 a, .tender-title a")
            if title_el:
                item["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                item["url"] = self.base_url + href if href.startswith("/") else href
                num_match = re.search(r"(\d{10,})", href + title_el.get_text())
                if num_match:
                    item["registry_number"] = num_match.group(1)

            price_el = block.select_one(".price, .sum, .nmck")
            if price_el:
                cleaned = re.sub(r"[^\d.]", "", price_el.get_text().replace(",", ".").replace(" ", ""))
                try:
                    item["nmck"] = float(cleaned)
                except ValueError:
                    pass

            customer_el = block.select_one(".customer, .organizer, .company")
            if customer_el:
                item["customer_name"] = customer_el.get_text(strip=True)

            deadline_el = block.select_one(".deadline, .end-date, time")
            if deadline_el:
                item["deadline"] = deadline_el.get_text(strip=True)

            if item.get("title"):
                items.append(item)

        return {"items": items}

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"]:
            try:
                return datetime.strptime(s.strip()[:19], fmt)
            except ValueError:
                continue
        return None

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            title = item.get("title") or item.get("name") or ""
            if not title:
                continue

            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number") or item.get("number"),
                law_type="44-fz",
                title=title,
                customer_name=item.get("customer_name") or item.get("customer", {}).get("name"),
                nmck=item.get("nmck") or item.get("start_price"),
                submission_deadline=self._parse_date(
                    item.get("deadline") or item.get("application_end_date", "")
                ),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = ["мебель", "подряд", "строительные работы", "ремонт"]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[Roseltorg] Searching: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        data = self._search(query, page)
                        items = data.get("items") or data.get("data") or []
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[Roseltorg] Total: {len(all_tenders)} tenders")
        return all_tenders
