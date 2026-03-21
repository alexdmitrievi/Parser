"""Парсер ЕИС через HTTP API (поиск на сайте zakupki.gov.ru).

Fallback для FTP — позволяет искать по ключевым словам,
фильтровать по ОКПД2, регионам, ценовому диапазону.
Покрывает и 44-ФЗ, и 223-ФЗ.
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


class EisApiScraper(BaseScraper):
    """Парсер поиска zakupki.gov.ru через HTTP."""

    platform = "eis"
    base_url = "https://zakupki.gov.ru"
    min_delay = 4.0
    max_delay = 8.0  # Госплощадка — уважаем rate limits

    SEARCH_URL = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"

    # Маппинг параметров поиска ЕИС
    LAW_MAP = {"44-fz": "FZ44", "223-fz": "FZ223", "pp615": "PP615"}

    def _build_search_params(
        self,
        query: str = "",
        law_type: str = "",
        region: str = "",
        price_from: float | None = None,
        price_to: float | None = None,
        okpd2: str = "",
        page: int = 1,
    ) -> dict:
        params = {
            "searchString": query,
            "morphology": "on",
            "search-filter": "Дата+размещения",
            "pageNumber": str(page),
            "sortDirection": "false",
            "recordsPerPage": "_50",
            "showLotsInfoHidden": "false",
            "sortBy": "UPDATE_DATE",
            "fz44": "on",
            "fz223": "on",
            "af": "on",
            "ca": "on",
            "pc": "on",
            "pa": "on",
        }

        if law_type and law_type in self.LAW_MAP:
            # Оставляем только нужный закон
            for key in ["fz44", "fz223"]:
                params.pop(key, None)
            if law_type == "44-fz":
                params["fz44"] = "on"
            elif law_type == "223-fz":
                params["fz223"] = "on"

        if price_from is not None:
            params["priceFromGeneral"] = str(int(price_from))
        if price_to is not None:
            params["priceToGeneral"] = str(int(price_to))

        if okpd2:
            params["okpd2Ids"] = okpd2

        return params

    def _parse_search_page(self, html: str) -> list[dict]:
        """Распарсить страницу результатов поиска ЕИС."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Блоки результатов поиска
        blocks = soup.select(".search-registry-entry-block, .registry-entry__form")

        for block in blocks:
            item = {}

            # Номер закупки
            num_el = block.select_one(".registry-entry__header-mid__number a, .header-mid__number a")
            if num_el:
                text = num_el.get_text(strip=True)
                item["registry_number"] = re.sub(r"[^\d]", "", text)
                href = num_el.get("href", "")
                if href:
                    item["url"] = self.base_url + href if href.startswith("/") else href

            # Название
            title_el = block.select_one(".registry-entry__body-value, .body-val")
            if title_el:
                item["title"] = title_el.get_text(strip=True)

            # Заказчик
            customer_el = block.select_one(".registry-entry__body-href a")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)

            # Цена
            price_el = block.select_one(".price-block__value")
            if price_el:
                price_text = price_el.get_text(strip=True)
                cleaned = re.sub(r"[^\d.,]", "", price_text.replace(",", "."))
                try:
                    item["nmck"] = float(cleaned)
                except ValueError:
                    pass

            # Даты
            dates = block.select(".data-block__value, .date-block__value")
            if len(dates) >= 2:
                item["publish_date"] = dates[0].get_text(strip=True)
                item["deadline"] = dates[1].get_text(strip=True)

            # Тип закона
            law_el = block.select_one(".registry-entry__header-top__title")
            if law_el:
                law_text = law_el.get_text(strip=True)
                if "44" in law_text:
                    item["law_type"] = "44-fz"
                elif "223" in law_text:
                    item["law_type"] = "223-fz"
                elif "615" in law_text:
                    item["law_type"] = "pp615"

            if item.get("title"):
                results.append(item)

        return results

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ["%d.%m.%Y", "%d.%m.%Y %H:%M"]:
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                continue
        return None

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type=item.get("law_type", "44-fz"),
                title=item["title"],
                customer_name=item.get("customer"),
                nmck=item.get("nmck"),
                publish_date=self._parse_date(item.get("publish_date", "")),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(
        self,
        queries: list[str] | None = None,
        max_pages: int = 3,
        law_type: str = "",
        price_from: float | None = None,
        price_to: float | None = None,
        **kwargs,
    ) -> list[TenderCreate]:
        if queries is None:
            queries = ["мебель", "подряд ремонт", "строительно-монтажные работы"]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[EIS API] Searching: {query}")

                for page in range(1, max_pages + 1):
                    params = self._build_search_params(
                        query=query, law_type=law_type,
                        price_from=price_from, price_to=price_to, page=page,
                    )
                    url = f"{self.SEARCH_URL}?{urlencode(params)}"

                    try:
                        resp = self.fetch(url)
                        items = self._parse_search_page(resp.text)

                        if not items:
                            break

                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")

                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        logger.info(f"[EIS API] Total: {len(all_tenders)} tenders")
        return all_tenders
