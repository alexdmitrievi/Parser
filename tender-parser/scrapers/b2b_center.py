"""Парсер B2B-Center (b2b-center.ru).

Крупнейшая коммерческая площадка РФ — ~30% коммерческих тендеров.
Парсит таблицу table.search-results на /market/.
Структура: 5 колонок — Название | Заказчик | Опубликовано | Дедлайн | Избранное.
Цена и регион в списке отсутствуют — только на странице тендера.
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

    def _parse_date(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        text = text.strip()
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Реальная структура: table.search-results > tr (первый — заголовок)
        table = soup.select_one("table.search-results")
        if not table:
            # Fallback: любая таблица с тендерными ссылками
            table = soup.find("table")
        if not table:
            return results

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            item = {}

            # Колонка 0: Название + ссылка
            link = cells[0].find("a")
            if link:
                title_text = link.get_text(strip=True)
                if not title_text or len(title_text) < 5:
                    continue
                item["title"] = title_text
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = self.base_url + href
                item["url"] = href
                # Номер из URL
                num_match = re.search(r"tender-(\d+)", href)
                if num_match:
                    item["registry_number"] = num_match.group(1)
            else:
                continue

            # Колонка 1: Заказчик
            if len(cells) > 1:
                cust_link = cells[1].find("a")
                if cust_link:
                    item["customer"] = cust_link.get_text(strip=True)
                else:
                    item["customer"] = cells[1].get_text(strip=True) or None

            # Колонка 2: Дата публикации
            if len(cells) > 2:
                item["publish_date"] = cells[2].get_text(strip=True)

            # Колонка 3: Дедлайн
            if len(cells) > 3:
                item["deadline"] = cells[3].get_text(strip=True)

            results.append(item)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="commercial",
                purchase_method=None,
                title=item["title"],
                customer_name=item.get("customer"),
                customer_region=None,  # Не доступен в списке
                nmck=None,  # Не доступен в списке
                publish_date=self._parse_date(item.get("publish_date", "")),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 5, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                # Поставки
                "поставка оборудования", "поставка материалов", "поставка запчастей",
                "поставка спецодежды", "поставка компьютеров",
                # Ремонт и строительство
                "ремонт", "капитальный ремонт", "строительство",
                "строительно-монтажные работы", "реконструкция",
                # Услуги
                "IT услуги", "транспортные услуги", "логистика",
                "уборка", "клининг", "охрана", "аутсорсинг",
                "техническое обслуживание", "сервисное обслуживание",
                # Товары
                "мебель", "продукты питания", "медицинское оборудование",
                "канцтовары", "химическая продукция", "металлопрокат",
                "электрооборудование", "трубная продукция",
                # Проекты
                "проектные работы", "инженерные изыскания",
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
