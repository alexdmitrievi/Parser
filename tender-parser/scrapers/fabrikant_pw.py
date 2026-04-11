"""Парсер Fabrikant (fabrikant.ru) через Playwright.

Fabrikant — крупная коммерческая площадка.
Сайт на Next.js (React), рендерит контент через JS.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from shared.models import TenderCreate
from scrapers.playwright_base import PlaywrightScraper

logger = logging.getLogger(__name__)


class FabrikantPlaywrightScraper(PlaywrightScraper):
    """Парсер fabrikant.ru через Playwright."""

    platform = "fabrikant"
    base_url = "https://www.fabrikant.ru"
    min_delay = 3.0
    max_delay = 6.0

    def _parse_date(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        text = text.strip()
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        return None

    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Паттерн для ссылок на конкретные тендеры (содержат числовой ID в пути)
        _trade_link = re.compile(r"/trades/[^?#]*\d+")
        # Ключевые слова нетендерного контента
        _skip_titles = re.compile(
            r"политик|персональных данных|cookie|куки|оферт|пользовательское соглашение",
            re.IGNORECASE,
        )

        # Fabrikant: карточки тендеров с data-id или внутри card-like div
        blocks = soup.select("div[data-id], div[data-slot='card'], div[class*='card']")

        if not blocks:
            # Fallback: только ссылки на конкретные тендеры (с числовым ID в пути)
            links = soup.find_all("a", href=lambda h: h and bool(_trade_link.search(h)))
            seen_parents: list = []
            for link in links:
                parent = link.find_parent("div", recursive=True)
                if parent and parent not in seen_parents:
                    seen_parents.append(parent)
                    blocks.append(parent)

        for block in blocks:
            item = {}
            data_id = block.get("data-id")

            # Ссылка на конкретный тендер (требуем числовой ID в пути)
            link = block.find("a", href=lambda h: h and bool(_trade_link.search(h)))
            if not link:
                continue
            title = link.get_text(strip=True)
            if not title or len(title) <= 5:
                continue
            # Пропускаем нетендерный контент (политики, оферты и т.д.)
            if _skip_titles.search(title):
                continue
            item["title"] = title
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = self.base_url + href
            item["url"] = href
            if data_id:
                item["registry_number"] = str(data_id)
            else:
                num_match = re.search(r"(\d+)", href.split("?")[0].rstrip("/").split("/")[-1])
                if num_match:
                    item["registry_number"] = num_match.group(1)

            if not item.get("title"):
                continue

            # Ищем текстовые блоки внутри карточки
            all_text = block.get_text(separator="\n")
            lines = [l.strip() for l in all_text.split("\n") if l.strip()]

            # Цена (ищем число с ₽ или руб)
            for line in lines:
                price_match = re.search(r"([\d\s,.]+)\s*(?:₽|руб)", line)
                if price_match:
                    item["nmck"] = self._parse_price(price_match.group(1))
                    break

            # Дата (ищем формат DD.MM.YYYY)
            for line in lines:
                date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", line)
                if date_match:
                    item["deadline"] = date_match.group(1)
                    break

            # Организация (ищем ООО, АО, ПАО, ГУП и т.д.)
            for line in lines:
                if re.search(r"(ООО|АО|ПАО|ГУП|МУП|ГБУ|МБУ|ФГУП|ОАО|ЗАО)", line):
                    item["customer"] = line[:200]
                    break

            results.append(item)

        return results

    def run(self, queries: list[str] | None = None, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "ремонт", "поставка оборудования", "строительство",
                "IT услуги", "мебель", "уборка", "охрана",
                "продукты питания", "транспортные услуги",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[Fabrikant PW] Searching: {query}")
                for page in range(1, max_pages + 1):
                    url = f"{self.base_url}/trades/procedure/search/?SearchString={query}&page={page}"
                    try:
                        html = self.goto(url, wait_selector="div[data-slot='card'], div[data-id], a[href*='/trades/procedure/']")
                        items = self._parse_page(html)
                        if not items:
                            logger.info(f"  Page {page}: no results, stopping")
                            break
                        for item in items:
                            all_tenders.append(TenderCreate(
                                source_platform=self.platform,
                                registry_number=item.get("registry_number"),
                                law_type="commercial",
                                title=item["title"],
                                customer_name=item.get("customer"),
                                customer_region=None,
                                nmck=item.get("nmck"),
                                submission_deadline=self._parse_date(item.get("deadline", "")),
                                original_url=item.get("url", ""),
                            ))
                        logger.info(f"  Page {page}: {len(items)} tenders")
                        self._delay()
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[Fabrikant PW] Total: {len(all_tenders)} tenders")
        return all_tenders
