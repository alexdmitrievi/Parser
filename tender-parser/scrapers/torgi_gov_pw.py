"""Парсер Торги.гов.ру через Playwright.

Официальный портал торгов РФ — государственное и муниципальное имущество,
земельные участки, конфискованное имущество, банкротства.
Сайт SPA (Angular) — рендерится через JavaScript.
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

BASE_URL = "https://torgi.gov.ru"

# Типы имущества по содержимому lot-biddtype
PROPERTY_MAP = {
    "земельн": "land",
    "аренда земел": "land",
    "недвижим": "real_estate",
    "нежил": "real_estate",
    "жил": "real_estate",
    "здани": "real_estate",
    "помещен": "real_estate",
    "транспорт": "vehicles",
    "автомобил": "vehicles",
    "оборудов": "equipment",
    "имущест": "other_assets",
    "реализац": "other_assets",
    "приватизац": "other_assets",
}


class TorgiGovPlaywrightScraper(PlaywrightScraper):
    """Парсер torgi.gov.ru через Playwright."""

    platform = "torgi_gov"
    base_url = BASE_URL
    min_delay = 3.0
    max_delay = 6.0

    def _detect_property_type(self, text: str) -> str:
        """Определить тип имущества по тексту."""
        lower = text.lower()
        for keyword, prop_type in PROPERTY_MAP.items():
            if keyword in lower:
                return prop_type
        return "other_assets"

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
        """Парсить HTML страницы с лотами."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        lots = soup.select("div.lotDescription")
        for lot in lots:
            item = {}

            # Название
            name_el = lot.select_one("div.lotName")
            if name_el:
                item["title"] = name_el.get_text(strip=True)

            if not item.get("title") or len(item["title"]) < 3:
                continue

            # Ссылка
            link_el = lot.select_one("a.lotLink")
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = self.base_url + href
                item["url"] = href

            # Регион
            region_el = lot.select_one("div.locationAddress, div.lotLocation")
            if region_el:
                item["region"] = region_el.get_text(strip=True)

            # Номер извещения
            notice_el = lot.select_one("a.notice-link")
            if notice_el:
                num_text = notice_el.get_text(strip=True)
                num_match = re.search(r"(\d{10,})", num_text)
                if num_match:
                    item["registry_number"] = num_match.group(1)

            # Тип торгов
            biddtype_el = lot.select_one("div.lot-biddtype")
            if biddtype_el:
                item["biddtype"] = biddtype_el.get_text(strip=True)

            # Тип имущества
            full_text = lot.get_text(strip=True)
            item["property_type"] = self._detect_property_type(
                (item.get("title", "") + " " + item.get("biddtype", "") + " " + full_text)
            )

            # Статус
            status_el = lot.select_one("span.inherit-styles")
            if status_el:
                item["status_text"] = status_el.get_text(strip=True)

            results.append(item)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="auction",
                title=item["title"],
                description=item.get("biddtype", ""),
                customer_name=None,
                customer_region=item.get("region"),
                nmck=None,
                original_url=item.get("url", ""),
                niche_tags=[item.get("property_type", "other_assets")],
            ))
        return tenders

    def run(self, max_pages: int = 10, **kwargs) -> list[TenderCreate]:
        all_items: list[dict] = []

        with self:
            url = f"{self.base_url}/new/public/lots/reg"
            logger.info(f"[Торги.гов.ру] Loading: {url}")

            html = self.goto(url, wait_selector="div.lotDescription", timeout=30000)
            items = self._parse_page(html)
            all_items.extend(items)
            logger.info(f"  Page 1: {len(items)} lots")

            # Scroll down to load more lots (infinite scroll)
            for page_num in range(2, max_pages + 1):
                if not items:
                    break
                self._delay()
                # Scroll to bottom to trigger lazy loading
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self._page.wait_for_timeout(2000)

                new_html = self._page.content()
                new_items = self._parse_page(new_html)

                # Deduplicate by checking new items vs all_items
                existing_urls = {i.get("url") for i in all_items}
                fresh = [i for i in new_items if i.get("url") not in existing_urls]

                if not fresh:
                    logger.info(f"  Page {page_num}: no new lots, stopping")
                    break

                all_items.extend(fresh)
                items = fresh
                logger.info(f"  Page {page_num}: {len(fresh)} new lots (total: {len(all_items)})")

        tenders = self.parse_tenders(all_items)
        logger.info(f"[Торги.гов.ру] Total: {len(tenders)} lots")
        return tenders
