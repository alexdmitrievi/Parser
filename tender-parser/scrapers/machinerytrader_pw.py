"""Парсер MachineryTrader.com через Playwright.

MachineryTrader рендерит листинги через JS, поэтому httpx получает пустой HTML.
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.playwright_base import PlaywrightScraper
from scrapers.cat_base import parse_price_with_currency, to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)


class MachineryTraderPlaywrightScraper(PlaywrightScraper):
    """Парсер machinerytrader.com — Playwright."""

    platform = "machinerytrader"
    base_url = "https://www.machinerytrader.com"
    min_delay = 4.0
    max_delay = 8.0

    def _build_url(self, page: int = 1) -> str:
        url = f"{self.base_url}/listings/construction-equipment/for-sale/CATERPILLAR"
        if page > 1:
            url += f"?page={page}"
        return url

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # MachineryTrader listings — try common selectors
        items = (
            soup.select("[data-listing-id]")
            or soup.select("div[id^='listing']")
            or soup.select("div.search-result-item")
            or soup.select("div[class*='listing']")
            or soup.select("tr[class*='listing']")
            or soup.select("div[class*='result-item']")
            or soup.select("div[class*='equipmentCard']")
        )

        for item in items:
            listing: dict = {}

            # Title + Link
            title_el = (
                item.select_one("a[class*='title']")
                or item.select_one("h2 a")
                or item.select_one("h3 a")
                or item.select_one("a[data-listing-title]")
                or item.select_one("span.listing-title")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                # Fallback: any link with /listings/ in href
                link = item.find("a", href=lambda h: h and "/listing/" in h)
                if link:
                    listing["title"] = link.get_text(strip=True)
                    listing["url"] = urljoin(self.base_url, link["href"])
                else:
                    continue

            if not listing.get("title") or len(listing["title"]) < 3:
                continue

            # Price
            price_el = (
                item.select_one("[class*='price']")
                or item.select_one("span.price")
            )
            if price_el:
                price_text = price_el.get_text(strip=True)
                listing["price"], listing["currency"] = parse_price_with_currency(price_text)
                if not listing.get("currency"):
                    listing["currency"] = "USD"

            # Location
            loc_el = (
                item.select_one("[class*='location']")
                or item.select_one("[class*='city']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID
            data_id = item.get("data-listing-id") or item.get("id", "")
            listing["id"] = str(data_id).replace("listing-", "") or hashlib.md5(
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
        seen: set[str] = set()

        with self:
            for page in range(1, max_pages + 1):
                try:
                    url = self._build_url(page)
                    logger.info(f"[MachineryTrader PW] Page {page}: {url}")
                    html = self.goto(url, wait_selector="[class*='listing'], [class*='result']")
                    items = self._parse_page(html)

                    if not items:
                        logger.info(f"  Page {page}: no items, stopping")
                        break

                    for item in items:
                        uid = item.get("id", "")
                        if uid not in seen:
                            seen.add(uid)
                            all_items.append(item)

                    logger.info(f"  Page {page}: {len(items)} items")
                    self._delay()
                except Exception as e:
                    logger.warning(f"  Error page {page}: {e}")
                    break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[MachineryTrader PW] Total: {len(tenders)} listings")
        return tenders
