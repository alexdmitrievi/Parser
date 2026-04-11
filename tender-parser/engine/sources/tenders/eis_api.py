"""EIS API source adapter (zakupki.gov.ru search).

Migrated from scrapers/eis_api.py — same parsing logic, driven by engine pipeline.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from engine.types import (
    SourceConfig, SourceCategory, FetchMethod, FetchResult, ParsedRecord,
    RateLimitConfig,
)
from engine.sources.base import BaseSourceAdapter
from engine.parsers.utils import parse_price, parse_date, clean_text
from engine.config.registry import get_registry
from shared.constants import RUSSIAN_REGIONS


# ── Region detection (from original EIS scraper) ──

_REGION_KEYWORDS: list[tuple[str, str]] = []


def _stem(word: str) -> str:
    for suffix in ("ского", "ской", "ская", "ский", "ском", "ских",
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
    if not customer_name:
        return None
    lower = customer_name.lower()
    words = re.split(r'[\s,;.\(\)\-/«»“”‘’]+', lower)
    for keyword, region in _REGION_KEYWORDS:
        for w in words:
            if w.startswith(keyword):
                return region
    return None


# ── EIS Search URL params ──

SEARCH_URL = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"


class EisApiSourceAdapter(BaseSourceAdapter):
    """Adapter for zakupki.gov.ru search results."""

    def discover(self) -> list[str]:
        """Build search URLs with EIS-specific param structure."""
        queries = self.config.search_queries or ["мебель", "подряд ремонт"]
        max_pages = self.config.max_pages or 3
        urls: list[str] = []

        for query in queries:
            for page in range(1, max_pages + 1):
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
                urls.append(f"{SEARCH_URL}?{urlencode(params)}")

        return urls

    def parse_listing(self, result: FetchResult) -> list[ParsedRecord]:
        soup = BeautifulSoup(result.content, "html.parser")
        records: list[ParsedRecord] = []

        blocks = soup.select(".search-registry-entry-block, .registry-entry__form")

        for block in blocks:
            # Registry number
            num_el = block.select_one(
                ".registry-entry__header-mid__number a, .header-mid__number a"
            )
            registry_number = None
            url = ""
            if num_el:
                registry_number = re.sub(r"[^\d]", "", num_el.get_text(strip=True))
                href = num_el.get("href", "")
                if href:
                    url = self.config.base_url + href if href.startswith("/") else href

            # Title
            title_el = block.select_one(".registry-entry__body-value, .body-val")
            title = clean_text(title_el.get_text()) if title_el else ""
            if not title:
                continue

            # Customer
            customer_el = block.select_one(".registry-entry__body-href a")
            customer = clean_text(customer_el.get_text()) if customer_el else None
            region = _detect_region(customer) if customer else None

            # Price
            price_el = block.select_one(".price-block__value")
            nmck = parse_price(price_el.get_text()) if price_el else None

            # Dates
            dates = block.select(".data-block__value, .date-block__value")
            publish_date = parse_date(dates[0].get_text(strip=True)) if len(dates) >= 1 else None
            deadline = parse_date(dates[1].get_text(strip=True)) if len(dates) >= 2 else None

            # Law type
            law_type = None
            law_el = block.select_one(".registry-entry__header-top__title")
            if law_el:
                law_text = law_el.get_text(strip=True)
                if "44" in law_text:
                    law_type = "44-fz"
                elif "223" in law_text:
                    law_type = "223-fz"
                elif "615" in law_text:
                    law_type = "pp615"

            records.append(ParsedRecord(
                source_id=self.config.source_id,
                registry_number=registry_number,
                title=title,
                original_url=url,
                nmck=nmck,
                customer_name=customer,
                customer_region=region,
                submission_deadline=deadline,
                publish_date=publish_date,
                law_type=law_type,
                raw_data={"html_block": str(block)[:500]},
            ))

        return records


# ── Config & registration ──

EIS_API_CONFIG = SourceConfig(
    source_id="eis_api",
    platform_name="eis",
    category=SourceCategory.TENDERS,
    base_url="https://zakupki.gov.ru",
    fetch_method=FetchMethod.HTTP,
    search_queries=["мебель", "подряд ремонт", "строительно-монтажные работы"],
    max_pages=3,
    rate_limit=RateLimitConfig(min_delay=10.0, max_delay=18.0),
    law_type_default="44-fz",
)


def register_eis_api() -> None:
    get_registry().register(EIS_API_CONFIG, EisApiSourceAdapter)


def get_eis_api_adapter() -> EisApiSourceAdapter:
    return EisApiSourceAdapter(EIS_API_CONFIG)
