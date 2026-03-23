"""Парсер Сбербанк-АСТ (sberbank-ast.ru) через Playwright.

Сбербанк-АСТ — федеральная ЭТП для 44-ФЗ.
Сайт на ASP.NET, частично рендерит JS. Таблицы загружаются динамически.
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


class SberbankAstPlaywrightScraper(PlaywrightScraper):
    """Парсер sberbank-ast.ru через Playwright."""

    platform = "sberbank_ast"
    base_url = "https://www.sberbank-ast.ru"
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

        # Сбербанк-АСТ: таблица закупок, или карточки
        rows = soup.select("table tr, div[class*='purchase'], div[class*='card'], div[class*='item']")

        for row in rows:
            item = {}

            # Ссылка на закупку
            link = row.find("a", href=lambda h: h and ("Purchase" in h or "purchase" in h or "tender" in h))
            if not link:
                link = row.find("a", href=lambda h: h and h.startswith("/") and len(h) > 5)
            if link:
                title = link.get_text(strip=True)
                if title and len(title) > 5:
                    item["title"] = title
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        href = self.base_url + href
                    item["url"] = href
                    num_match = re.search(r"(\d{10,})", title + href)
                    if num_match:
                        item["registry_number"] = num_match.group(1)

            if not item.get("title"):
                continue

            # Ищем данные в ячейках таблицы
            cells = row.find_all("td")
            for cell in cells:
                text = cell.get_text(strip=True)
                # Цена
                if re.search(r"\d[\d\s,.]+₽|руб", text):
                    price = self._parse_price(text)
                    if price and not item.get("nmck"):
                        item["nmck"] = price
                # Дата
                date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
                if date_match and not item.get("deadline"):
                    item["deadline"] = date_match.group(1)

            # Заказчик
            all_text = row.get_text(separator="\n")
            for line in all_text.split("\n"):
                line = line.strip()
                if re.search(r"(ООО|АО|ПАО|ГУП|МУП|ГБУ|ФГУП|ОАО|ЗАО|МБУ|ГКУ|ГБОУ)", line) and not item.get("customer"):
                    item["customer"] = line[:200]
                    break

            results.append(item)

        return results

    def run(self, queries: list[str] | None = None, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "ремонт", "поставка", "строительство",
                "IT", "мебель", "уборка", "оборудование",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[Sberbank-AST PW] Searching: {query}")
                url = f"{self.base_url}/purchaseList.aspx"
                try:
                    html = self.goto(url, wait_selector="table", timeout=20000)

                    # Вводим поисковый запрос
                    search_input = self._page.query_selector("input[type='text'][id*='Search'], input[type='text'][id*='search'], input[name*='search']")
                    if search_input:
                        search_input.fill(query)
                        # Ищем кнопку поиска
                        btn = self._page.query_selector("input[type='submit'], button[type='submit'], a[id*='Search'], a[id*='search']")
                        if btn:
                            btn.click()
                            self._page.wait_for_timeout(3000)
                            html = self._page.content()

                    items = self._parse_page(html)
                    if items:
                        for item in items:
                            all_tenders.append(TenderCreate(
                                source_platform=self.platform,
                                registry_number=item.get("registry_number"),
                                law_type="44-fz",
                                title=item["title"],
                                customer_name=item.get("customer"),
                                customer_region=None,
                                nmck=item.get("nmck"),
                                submission_deadline=self._parse_date(item.get("deadline", "")),
                                original_url=item.get("url", ""),
                            ))
                        logger.info(f"  {query}: {len(items)} tenders")
                    else:
                        logger.info(f"  {query}: no results")

                    self._delay()
                except Exception as e:
                    logger.warning(f"  Error: {e}")

        logger.info(f"[Sberbank-AST PW] Total: {len(all_tenders)} tenders")
        return all_tenders
