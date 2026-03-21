"""Парсер B2B-Center (b2b-center.ru).

Крупнейшая коммерческая площадка РФ — ~30% коммерческих тендеров.
Поиск доступен без авторизации. JSON API.
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


class B2BCenterScraper(BaseScraper):
    """Парсер b2b-center.ru."""

    platform = "b2b_center"
    base_url = "https://www.b2b-center.ru"
    min_delay = 3.0
    max_delay = 7.0

    SEARCH_URL = "https://www.b2b-center.ru/market/"

    def _build_url(self, query: str, page: int = 1) -> str:
        params = {"query": query, "page": str(page)}
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.replace(",", ".").replace(" ", ""))
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_date(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        for fmt in ["%d.%m.%Y", "%d.%m.%Y %H:%M", "%d %B %Y"]:
            try:
                return datetime.strptime(text.strip(), fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # B2B-Center: блоки тендеров в таблице или списке
        blocks = soup.select(
            ".search-results-item, .tender-list-item, "
            "table.search-results tr, .market-item, "
            ".lot-item, article.tender"
        )

        for block in blocks:
            item = {}

            # Ссылка + заголовок
            link = block.select_one("a.tender-title, a.lot-title, h3 a, h2 a, a[href*='/market/']")
            if link:
                item["title"] = link.get_text(strip=True)
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = self.base_url + href
                item["url"] = href

                # Извлекаем номер из URL или текста
                num_match = re.search(r"/(\d{5,})", href)
                if num_match:
                    item["registry_number"] = num_match.group(1)

            if not item.get("title"):
                # Пробуем любой текстовый блок
                td = block.select_one("td:first-child a, .title")
                if td:
                    item["title"] = td.get_text(strip=True)
                    href = td.get("href", "")
                    if href:
                        item["url"] = self.base_url + href if not href.startswith("http") else href

            if not item.get("title"):
                continue

            # Заказчик / организатор
            org = block.select_one(".organizer, .customer, .company-name, td:nth-child(2)")
            if org:
                item["customer"] = org.get_text(strip=True)

            # Цена
            price = block.select_one(".price, .sum, .tender-price, td.price")
            if price:
                item["nmck"] = self._parse_price(price.get_text())

            # Дата окончания
            date_el = block.select_one(".date-end, .deadline, time, td.date")
            if date_el:
                item["deadline"] = date_el.get_text(strip=True)

            # Тип (конкурс, аукцион и т.д.)
            type_el = block.select_one(".type, .tender-type, .procedure-type")
            if type_el:
                item["method"] = type_el.get_text(strip=True)

            # Регион
            region_el = block.select_one(".region, .location, .delivery-place")
            if region_el:
                item["region"] = region_el.get_text(strip=True)

            results.append(item)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            method = (item.get("method") or "").lower()
            purchase_method = "other"
            if "аукцион" in method:
                purchase_method = "auction"
            elif "конкурс" in method:
                purchase_method = "contest"
            elif "котировк" in method or "запрос цен" in method:
                purchase_method = "quotation"

            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="commercial",
                purchase_method=purchase_method,
                title=item["title"],
                customer_name=item.get("customer"),
                customer_region=item.get("region"),
                nmck=item.get("nmck"),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "мебель", "мягкая мебель", "офисная мебель",
                "подряд строительство", "ремонт помещений", "отделочные работы",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[B2B-Center] Searching: {query}")

                for page in range(1, max_pages + 1):
                    url = self._build_url(query, page)
                    try:
                        resp = self.fetch(url)
                        items = self._parse_page(resp.text)
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        logger.info(f"[B2B-Center] Total: {len(all_tenders)} tenders")
        return all_tenders
