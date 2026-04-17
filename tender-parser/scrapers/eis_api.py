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
from shared.constants import RUSSIAN_REGIONS, EIS_REGION_IDS
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Маппинг корней слов из названий регионов → регион
_REGION_KEYWORDS: list[tuple[str, str]] = []

def _stem(word: str) -> str:
    """Грубая стемминг: убираем типичные окончания."""
    for suffix in ("ского", "ской", "ская", "ский", "ском", "ских", "ская",
                   "ного", "ной", "ная", "ный", "ном", "ных",
                   "кого", "кой", "кая", "кий", "ком", "ких",
                   "ого", "ой", "ая", "ый", "ом", "ых", "ий"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word

for _r in RUSSIAN_REGIONS:
    _lower = _r.lower().replace(" — ", " ")
    for _word in _lower.split():
        if _word in ("край", "область", "округ", "республика", "автономная", "автономный", "еврейская"):
            continue
        stem = _stem(_word)
        if len(stem) >= 3:
            _REGION_KEYWORDS.append((stem, _r))

# Сортируем по убыванию длины стема — длинные matчатся первыми
_REGION_KEYWORDS.sort(key=lambda x: len(x[0]), reverse=True)

# Явные паттерны для надёжности (добавляются в начало для приоритета)
_EXPLICIT_REGION_KEYWORDS = [
    ("москв", "Москва"), ("московск", "Московская область"),
    ("петербург", "Санкт-Петербург"), ("ленинградск", "Ленинградская область"),
    ("севастопол", "Севастополь"), ("крымск", "Республика Крым"),
    ("новосибирск", "Новосибирская область"), ("омск", "Омская область"),
    ("екатеринбург", "Свердловская область"), ("краснодар", "Краснодарский край"),
    ("красноярск", "Красноярский край"), ("казан", "Республика Татарстан"),
    ("тюмен", "Тюменская область"), ("челябинск", "Челябинская область"),
    ("самар", "Самарская область"), ("нижегородск", "Нижегородская область"),
    ("ростов", "Ростовская область"), ("воронеж", "Воронежская область"),
    ("волгоград", "Волгоградская область"), ("башкорт", "Республика Башкортостан"),
    ("новгородск", "Новгородская область"), ("пермск", "Пермский край"),
    ("костромск", "Костромская область"), ("томск", "Томская область"),
]
_EXPLICIT_REGION_KEYWORDS.sort(key=lambda x: len(x[0]), reverse=True)
_REGION_KEYWORDS = _EXPLICIT_REGION_KEYWORDS + _REGION_KEYWORDS


def _detect_region(customer_name: str) -> Optional[str]:
    """Определить регион из названия заказчика (word-boundary matching)."""
    if not customer_name:
        return None
    lower = customer_name.lower()
    # Разбиваем на слова — keyword должен совпадать с началом слова,
    # а не быть подстрокой внутри слова (предотвращает "омск" in "костромской")
    words = re.split(r'[\s,;.\(\)\-/«»“”‘’]+', lower)
    for keyword, region in _REGION_KEYWORDS:
        for w in words:
            if w.startswith(keyword):
                return region
    return None


class EisApiScraper(BaseScraper):
    """Парсер поиска zakupki.gov.ru через HTTP."""

    platform = "eis"
    base_url = "https://zakupki.gov.ru"
    min_delay = 10.0
    max_delay = 18.0  # Госплощадка — большие задержки, чтобы не заблокировали

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

        if region:
            eis_id = EIS_REGION_IDS.get(region)
            if eis_id:
                params["regions"] = eis_id

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

    def parse_tenders(self, raw_items: list[dict], forced_region: str = "") -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            customer = item.get("customer", "")
            region = _detect_region(customer) or forced_region or None
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type=item.get("law_type", "44-fz"),
                title=item["title"],
                customer_name=customer,
                customer_region=region,
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
        region: str = "",
        price_from: float | None = None,
        price_to: float | None = None,
        **kwargs,
    ) -> list[TenderCreate]:
        if queries is None:
            queries = ["мебель", "подряд ремонт", "строительно-монтажные работы"]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[EIS API] Searching: {query}" + (f" | region={region}" if region else ""))

                for page in range(1, max_pages + 1):
                    params = self._build_search_params(
                        query=query, law_type=law_type, region=region,
                        price_from=price_from, price_to=price_to, page=page,
                    )
                    url = f"{self.SEARCH_URL}?{urlencode(params)}"

                    try:
                        resp = self.fetch(url)
                        items = self._parse_search_page(resp.text)

                        if not items:
                            break

                        tenders = self.parse_tenders(items, forced_region=region)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")

                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        logger.info(f"[EIS API] Total: {len(all_tenders)} tenders")
        return all_tenders
