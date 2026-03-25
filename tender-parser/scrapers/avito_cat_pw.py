"""Парсер Avito.ru — б/у спецтехника Caterpillar через Playwright.

Avito блокирует httpx-запросы (антибот/captcha).
Playwright обходит JS-рендеринг и базовую защиту.
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.playwright_base import PlaywrightScraper
from scrapers.cat_base import parse_price, to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

SEARCH_QUERIES = ["caterpillar", "CAT экскаватор", "CAT бульдозер"]
BASE_SEARCH_URL = "https://www.avito.ru/rossiya/gruzoviki_i_spetstekhnika/spectehnika-ASg"


class AvitoCatPlaywrightScraper(PlaywrightScraper):
    """Парсер Avito.ru (спецтехника CAT) через Playwright."""

    platform = "avito_cat"
    base_url = "https://www.avito.ru"
    min_delay = 5.0
    max_delay = 10.0

    def _build_url(self, query: str, page: int = 1) -> str:
        url = f"{BASE_SEARCH_URL}?q={query}"
        if page > 1:
            url += f"&p={page}"
        return url

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        items = (
            soup.select("[data-marker='item']")
            or soup.select("[itemtype='http://schema.org/Product']")
            or soup.select("div[class*='iva-item']")
        )

        for item in items:
            listing: dict = {}

            # Title + Link
            title_el = (
                item.select_one("[data-marker='item-title']")
                or item.select_one("[itemprop='name']")
                or item.select_one("a[class*='title']")
                or item.select_one("h3 a")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if not href:
                    link = title_el.find_parent("a") or title_el.find("a")
                    if link:
                        href = link.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                continue

            if not listing.get("title") or len(listing["title"]) < 5:
                continue

            # Filter: only CAT/Caterpillar
            title_lower = listing["title"].lower()
            if not any(kw in title_lower for kw in ("cat", "caterpillar", "катерпиллер", "катерпиллар")):
                continue

            # Price (RUB)
            price_el = (
                item.select_one("[data-marker='item-price']")
                or item.select_one("[itemprop='price']")
                or item.select_one("[class*='price']")
            )
            if price_el:
                price_val = price_el.get("content")
                if price_val:
                    try:
                        listing["price"] = float(price_val)
                    except ValueError:
                        listing["price"] = parse_price(price_el.get_text())
                else:
                    listing["price"] = parse_price(price_el.get_text())

            # Location
            loc_el = (
                item.select_one("[class*='geo']")
                or item.select_one("[data-marker='item-address']")
                or item.select_one("[class*='location']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID
            data_id = item.get("data-item-id") or item.get("id", "")
            if data_id:
                listing["id"] = str(data_id)
            elif listing.get("url"):
                m = re.search(r"_(\d+)$", listing["url"])
                listing["id"] = m.group(1) if m else hashlib.md5(
                    listing["url"].encode()
                ).hexdigest()[:16]

            results.append(listing)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        return [
            to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency="RUB",
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
            )
            for item in raw_items
        ]

    def run(self, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        all_items: list[dict] = []
        seen_ids: set[str] = set()

        with self:
            for query in SEARCH_QUERIES:
                logger.info(f"[Avito PW] Query: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        url = self._build_url(query, page)
                        html = self.goto(url, wait_selector="[data-marker='item'], [class*='iva-item']")

                        # Check for captcha
                        if "captcha" in html.lower() or "blocked" in html.lower():
                            logger.warning(f"[Avito PW] Captcha/block detected, skipping")
                            break

                        items = self._parse_page(html)
                        if not items:
                            logger.info(f"  Page {page}: no items")
                            break

                        for item in items:
                            uid = item.get("id", "")
                            if uid and uid not in seen_ids:
                                seen_ids.add(uid)
                                all_items.append(item)

                        logger.info(f"  Page {page}: {len(items)} items")
                        self._delay()
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[Avito PW] Total: {len(tenders)} listings")
        return tenders
