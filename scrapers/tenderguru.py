"""Парсер агрегатора TenderGuru (tenderguru.ru).

Самый простой для парсинга — статический HTML, не требует JS.
Вторичный источник, но быстрый для получения данных.
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


class TenderGuruScraper(BaseScraper):
    """Парсер tenderguru.ru."""

    platform = "tenderguru"
    base_url = "https://www.tenderguru.ru"
    min_delay = 3.0
    max_delay = 7.0

    def _build_search_url(self, query: str, page: int = 1) -> str:
        params = {"query": query, "page": str(page)}
        return f"{self.base_url}/search?{urlencode(params)}"

    def _parse_price(self, price_str: str) -> Optional[float]:
        """Извлечь числовое значение цены из строки."""
        if not price_str:
            return None
        cleaned = re.sub(r"[^\d.,]", "", price_str.replace(",", "."))
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Распарсить дату из формата ДД.ММ.ГГГГ."""
        if not date_str:
            return None
        for fmt in ["%d.%m.%Y", "%d.%m.%Y %H:%M", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        """Распарсить одну страницу результатов поиска."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # TenderGuru выдаёт тендеры в блоках (адаптировать под актуальную вёрстку)
        tender_blocks = soup.select(".search-result-item, .tender-item, .result-item, article")

        for block in tender_blocks:
            item = {}

            # Заголовок и ссылка
            title_el = block.select_one("a.title, h3 a, h2 a, .tender-title a")
            if title_el:
                item["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = self.base_url + href
                item["url"] = href
            else:
                # Если нет ссылки с заголовком, пробуем текстовый блок
                title_el = block.select_one(".title, h3, h2")
                if title_el:
                    item["title"] = title_el.get_text(strip=True)

            if not item.get("title"):
                continue

            # Номер закупки
            num_el = block.select_one(".number, .tender-number, .reg-number")
            if num_el:
                item["registry_number"] = num_el.get_text(strip=True).replace("№", "").strip()

            # Цена
            price_el = block.select_one(".price, .tender-price, .nmck, .sum")
            if price_el:
                item["price"] = self._parse_price(price_el.get_text())

            # Заказчик
            customer_el = block.select_one(".customer, .organization, .company")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)

            # Регион
            region_el = block.select_one(".region, .location, .address")
            if region_el:
                item["region"] = region_el.get_text(strip=True)

            # Дедлайн
            date_el = block.select_one(".deadline, .end-date, .date-end, time")
            if date_el:
                item["deadline"] = date_el.get_text(strip=True)

            # Тип закупки
            type_el = block.select_one(".type, .purchase-type, .law-type")
            if type_el:
                item["law_type"] = type_el.get_text(strip=True)

            results.append(item)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        """Конвертировать сырые данные в TenderCreate."""
        tenders = []
        for item in raw_items:
            # Определяем тип закона
            law_type = "commercial"
            law_text = item.get("law_type", "").lower()
            if "44" in law_text:
                law_type = "44-fz"
            elif "223" in law_text:
                law_type = "223-fz"

            tender = TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type=law_type,
                title=item["title"],
                customer_name=item.get("customer"),
                customer_region=item.get("region"),
                nmck=item.get("price"),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            )
            tenders.append(tender)

        return tenders

    def run(self, queries: Optional[list[str]] = None, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг TenderGuru по списку запросов."""
        if queries is None:
            queries = ["мебель", "подряд строительство", "ремонт помещений"]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[TenderGuru] Searching: {query}")

                for page in range(1, max_pages + 1):
                    url = self._build_search_url(query, page)

                    try:
                        response = self.fetch(url)
                        raw_items = self._parse_page(response.text)

                        if not raw_items:
                            logger.info(f"  Page {page}: no results, stopping")
                            break

                        tenders = self.parse_tenders(raw_items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")

                    except Exception as e:
                        logger.warning(f"  Error on page {page}: {e}")
                        break

        logger.info(f"[TenderGuru] Total: {len(all_tenders)} tenders")
        return all_tenders
