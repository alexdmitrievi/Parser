"""B2B-Center source adapter (b2b-center.ru).

Migrated from scrapers/b2b_center.py — same parsing logic.
B2B-Center has a table-based listing (table.search-results)
with 5 cols: Название | Заказчик | Опубликовано | Дедлайн | Избранное.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from engine.types import (
    SourceConfig, SourceCategory, FetchMethod, FetchResult, ParsedRecord,
    RateLimitConfig,
)
from engine.sources.base import BaseSourceAdapter
from engine.parsers.utils import parse_price, parse_date, clean_text
from engine.config.registry import get_registry


class B2BCenterSourceAdapter(BaseSourceAdapter):
    """Adapter for b2b-center.ru search results."""

    def parse_listing(self, result: FetchResult) -> list[ParsedRecord]:
        soup = BeautifulSoup(result.content, "html.parser")
        records: list[ParsedRecord] = []

        table = soup.select_one("table.search-results")
        if not table:
            table = soup.find("table")
        if not table:
            return records

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            # Col 0: Title + link
            link = cells[0].find("a")
            if not link:
                continue

            title_text = clean_text(link.get_text())
            if not title_text or len(title_text) < 5:
                continue

            # Strip procedure prefix
            title_text = re.sub(
                r"^(?:Процедура закупки|Запрос предложений|Запрос цен|"
                r"Запрос котировок|Конкурс|Аукцион)\s*№?\s*\d+/?\.?\s*\d*",
                "", title_text,
            ).strip()
            if not title_text or len(title_text) < 5:
                title_text = clean_text(link.get_text())

            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = self.config.base_url + href

            # Registry number from URL
            num_match = re.search(r"tender-(\d+)", href)
            reg_num = num_match.group(1) if num_match else None

            # Col 1: Customer
            customer = None
            if len(cells) > 1:
                cust_link = cells[1].find("a")
                customer = clean_text(cust_link.get_text()) if cust_link else clean_text(cells[1].get_text())

            # Col 2: Publish date
            publish_date = parse_date(cells[2].get_text(strip=True)) if len(cells) > 2 else None

            # Col 3: Deadline
            deadline = parse_date(cells[3].get_text(strip=True)) if len(cells) > 3 else None

            records.append(ParsedRecord(
                source_id=self.config.source_id,
                registry_number=reg_num,
                title=title_text,
                original_url=href,
                customer_name=customer,
                publish_date=publish_date,
                submission_deadline=deadline,
                law_type="commercial",
                raw_data={"html_row": str(row)[:500]},
            ))

        return records


# ── Config ──

B2B_CENTER_CONFIG = SourceConfig(
    source_id="b2b_center",
    platform_name="b2b_center",
    category=SourceCategory.TENDERS,
    base_url="https://www.b2b-center.ru",
    fetch_method=FetchMethod.HTTP,
    search_queries=[
        "ремонт", "капитальный ремонт", "строительство",
        "строительно-монтажные работы", "реконструкция",
        "фасадные работы", "кровельные работы", "отделочные работы",
        "мазут", "печное топливо", "дизельное топливо", "ГСМ",
        "поставка оборудования", "поставка материалов",
        "поставка спецодежды", "металлопрокат",
        "IT услуги", "транспортные услуги", "клининг",
        "техническое обслуживание", "проектные работы",
        "мебель", "продукты питания", "медицинское оборудование",
        "утилизация", "озеленение", "страхование",
    ],
    max_pages=5,
    endpoints={
        "search": "/market/",
        "query_param": "query",
        "page_param": "page",
    },
    rate_limit=RateLimitConfig(min_delay=3.0, max_delay=7.0),
    law_type_default="commercial",
)


def register_b2b_center() -> None:
    get_registry().register(B2B_CENTER_CONFIG, B2BCenterSourceAdapter)


def get_b2b_center_adapter() -> B2BCenterSourceAdapter:
    return B2BCenterSourceAdapter(B2B_CENTER_CONFIG)
