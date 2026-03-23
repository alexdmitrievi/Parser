"""Парсер ТЭК-Торг (tektorg.ru) через Playwright.

ТЭК-Торг — федеральная ЭТП, специализация 223-ФЗ.
Сайт рендерит контент через JS, поэтому нужен Playwright.
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


class TekTorgPlaywrightScraper(PlaywrightScraper):
    """Парсер tektorg.ru через Playwright."""

    platform = "tektorg"
    base_url = "https://www.tektorg.ru"
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
            return float(cleaned) if float(cleaned) > 0 else None
        except ValueError:
            return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Ищем блоки процедур по разным возможным селекторам
        blocks = soup.select(
            "div[class*='procedure-card'], div[class*='procedure-item'], "
            "div[class*='search-item'], article, div[class*='card']"
        )

        if not blocks:
            # Fallback: ищем ссылки на процедуры
            links = soup.find_all("a", href=lambda h: h and "/procedure/" in h)
            for link in links:
                parent = link.find_parent("div") or link.find_parent("tr")
                if parent and parent not in blocks:
                    blocks.append(parent)

        for block in blocks:
            item = {}

            # Ссылка и заголовок
            link = block.find("a", href=lambda h: h and "/procedure/" in h)
            if not link:
                link = block.find("a", href=lambda h: h and ("/tender" in h or "/lot" in h))
            if link:
                item["title"] = link.get_text(strip=True)
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = self.base_url + href
                item["url"] = href
                num_match = re.search(r"(\d{8,})", href)
                if num_match:
                    item["registry_number"] = num_match.group(1)

            if not item.get("title") or len(item["title"]) < 5:
                continue

            # Цена
            for sel in [".price", ".nmck", ".sum", "[class*=price]", "[class*=sum]"]:
                el = block.select_one(sel)
                if el:
                    item["nmck"] = self._parse_price(el.get_text())
                    break

            # Заказчик
            for sel in [".customer", ".organizer", ".company", "[class*=customer]", "[class*=organizer]"]:
                el = block.select_one(sel)
                if el:
                    item["customer"] = el.get_text(strip=True)
                    break

            # Регион
            for sel in [".region", ".location", "[class*=region]", "[class*=location]"]:
                el = block.select_one(sel)
                if el:
                    item["region"] = el.get_text(strip=True)
                    break

            # Дедлайн
            for sel in [".deadline", ".end-date", "[class*=deadline]", "[class*=end-date]", "time"]:
                el = block.select_one(sel)
                if el:
                    item["deadline"] = el.get_text(strip=True)
                    break

            results.append(item)

        return results

    def run(self, queries: list[str] | None = None, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "ремонт", "поставка оборудования", "строительство",
                "IT услуги", "мебель", "уборка", "транспортные услуги",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[TekTorg PW] Searching: {query}")
                for page in range(1, max_pages + 1):
                    url = f"{self.base_url}/procedures?search={query}&page={page}"
                    try:
                        html = self.goto(url, wait_selector="a[href*='/procedure/']")
                        items = self._parse_page(html)
                        if not items:
                            logger.info(f"  Page {page}: no results, stopping")
                            break
                        for item in items:
                            all_tenders.append(TenderCreate(
                                source_platform=self.platform,
                                registry_number=item.get("registry_number"),
                                law_type="223-fz",
                                title=item["title"],
                                customer_name=item.get("customer"),
                                customer_region=item.get("region"),
                                nmck=item.get("nmck"),
                                submission_deadline=self._parse_date(item.get("deadline", "")),
                                original_url=item.get("url", ""),
                            ))
                        logger.info(f"  Page {page}: {len(items)} tenders")
                        self._delay()
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[TekTorg PW] Total: {len(all_tenders)} tenders")
        return all_tenders
