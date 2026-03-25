"""Парсер catused.cat.com — официальный портал б/у CAT через Playwright.

Сайт — SPA (Single Page Application), данные подгружаются через JS.
"""

from __future__ import annotations

import hashlib
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.playwright_base import PlaywrightScraper
from scrapers.cat_base import parse_price_with_currency, to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)


class CatUsedPlaywrightScraper(PlaywrightScraper):
    """Парсер catused.cat.com через Playwright."""

    platform = "catused"
    base_url = "https://catused.cat.com"
    min_delay = 3.0
    max_delay = 6.0

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # CAT Used — try common selectors for equipment cards
        items = (
            soup.select("[class*='equipment-card']")
            or soup.select("[class*='product-card']")
            or soup.select("[class*='listing']")
            or soup.select("[class*='EquipmentCard']")
            or soup.select("div.card")
            or soup.select("article")
        )

        for item in items:
            listing: dict = {}

            # Title + Link
            title_el = (
                item.select_one("h2 a") or item.select_one("h3 a")
                or item.select_one("a[class*='title']")
                or item.select_one("[class*='name']")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                h_tag = item.select_one("h2") or item.select_one("h3")
                if h_tag:
                    listing["title"] = h_tag.get_text(strip=True)
                    link = h_tag.find("a")
                    if link and link.get("href"):
                        listing["url"] = urljoin(self.base_url, link["href"])
                else:
                    continue

            if not listing.get("title") or len(listing["title"]) < 3:
                continue

            # Price
            price_el = item.select_one("[class*='price']")
            if price_el:
                listing["price"], listing["currency"] = parse_price_with_currency(
                    price_el.get_text(strip=True)
                )

            # Location
            loc_el = (
                item.select_one("[class*='location']")
                or item.select_one("[class*='dealer']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID
            data_id = item.get("data-id") or item.get("data-equipment-id", "")
            listing["id"] = str(data_id) if data_id else hashlib.md5(
                (listing.get("url") or listing["title"]).encode()
            ).hexdigest()[:16]

            results.append(listing)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        return [
            to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency=item.get("currency", "USD"),
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
            )
            for item in raw_items
        ]

    def run(self, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        all_items: list[dict] = []

        with self:
            for page in range(1, max_pages + 1):
                try:
                    url = f"{self.base_url}/en/equipment"
                    if page > 1:
                        url += f"?page={page}"
                    logger.info(f"[CAT Used PW] Page {page}: {url}")
                    html = self.goto(
                        url,
                        wait_selector="[class*='card'], [class*='equipment'], article",
                    )
                    items = self._parse_page(html)

                    if not items:
                        logger.info(f"  Page {page}: no items, stopping")
                        break

                    all_items.extend(items)
                    logger.info(f"  Page {page}: {len(items)} items")
                    self._delay()
                except Exception as e:
                    logger.warning(f"  Error page {page}: {e}")
                    break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[CAT Used PW] Total: {len(tenders)} listings")
        return tenders
