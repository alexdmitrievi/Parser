"""Парсер Kolesa.kz — спецтехника Caterpillar через Playwright.

Kolesa.kz рендерит карточки через JS. Playwright ждёт загрузки контента.
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


class KolesaKzPlaywrightScraper(PlaywrightScraper):
    """Парсер kolesa.kz (спецтехника CAT) через Playwright."""

    platform = "kolesa_kz"
    base_url = "https://kolesa.kz"
    min_delay = 3.0
    max_delay = 6.0

    def _build_url(self, page: int = 1) -> str:
        url = f"{self.base_url}/spectehnika/?text=caterpillar"
        if page > 1:
            url += f"&page={page}"
        return url

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Kolesa.kz cards — try multiple selectors
        items = (
            soup.select("div.a-card")
            or soup.select("[class*='a-card']")
            or soup.select("[data-id]")
            or soup.select("div[class*='CardNew']")
            or soup.select("div[class*='card']")
            or soup.select("a[class*='a-card']")
        )

        for item in items:
            listing: dict = {}

            # Title + Link
            title_el = (
                item.select_one("a.a-card__title")
                or item.select_one("a[class*='title']")
                or item.select_one("h3 a")
                or item.select_one("a[class*='name']")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                # The card itself might be a link
                if item.name == "a" and item.get("href"):
                    listing["title"] = item.get_text(strip=True)[:120]
                    listing["url"] = urljoin(self.base_url, item["href"])
                else:
                    link = item.find("a", href=True)
                    if link:
                        listing["title"] = link.get_text(strip=True)
                        listing["url"] = urljoin(self.base_url, link["href"])
                    else:
                        continue

            if not listing.get("title") or len(listing["title"]) < 3:
                continue

            # Price (KZT)
            price_el = (
                item.select_one("[class*='price']")
                or item.select_one("[class*='cost']")
            )
            if price_el:
                listing["price"] = parse_price(price_el.get_text())

            # Location
            loc_el = (
                item.select_one("[class*='param']")
                or item.select_one("[class*='city']")
                or item.select_one("[class*='location']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID
            data_id = item.get("data-id") or item.get("id", "")
            if data_id:
                listing["id"] = str(data_id)
            elif listing.get("url"):
                m = re.search(r"/(\d+)/?$", listing["url"])
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
                currency="KZT",
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
                description=item.get("description"),
            )
            for item in raw_items
        ]

    def run(self, max_pages: int = 5, **kwargs) -> list[TenderCreate]:
        all_items: list[dict] = []

        with self:
            for page in range(1, max_pages + 1):
                try:
                    url = self._build_url(page)
                    logger.info(f"[Kolesa.kz PW] Page {page}: {url}")
                    html = self.goto(url, wait_selector="[class*='card'], [data-id]")
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
        logger.info(f"[Kolesa.kz PW] Total: {len(tenders)} listings")
        return tenders
