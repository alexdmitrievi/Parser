"""Парсер MachineryTrader.com — крупнейший маркетплейс строительной техники.

Ищет б/у Caterpillar: экскаваторы, бульдозеры, погрузчики и т.д.
URL: machinerytrader.com/listings/construction-equipment/for-sale/CATERPILLAR
"""

from __future__ import annotations

import hashlib
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.cat_base import parse_price_with_currency, to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# Категории для поиска
SEARCH_CATEGORIES = [
    "construction-equipment",
    "mining-equipment",
]


class MachineryTraderScraper(BaseScraper):
    """Парсер machinerytrader.com — б/у Caterpillar."""

    platform = "machinerytrader"
    base_url = "https://www.machinerytrader.com"
    min_delay = 3.0
    max_delay = 8.0
    timeout = 45.0

    def _build_url(self, category: str, page: int = 1) -> str:
        """Построить URL листинга."""
        url = f"{self.base_url}/listings/{category}/for-sale/CATERPILLAR"
        if page > 1:
            url += f"?page={page}"
        return url

    def _parse_listing_page(self, html: str) -> list[dict]:
        """Парсить страницу со списком."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # MachineryTrader: listings in divs/table rows
        items = (
            soup.select("div[id^='listing-']")
            or soup.select("div.listing")
            or soup.select("div[class*='result']")
            or soup.select("div[data-listing]")
            or soup.select("tr[class*='listing']")
        )

        if not items:
            # Broader fallback
            items = soup.select("div.search-result-item") or soup.select("article")

        for item in items:
            listing: dict = {}

            # Title
            title_el = (
                item.select_one("a.listing-title")
                or item.select_one("h2 a")
                or item.select_one("a[class*='title']")
                or item.select_one("span.listing-title")
                or item.select_one("a[data-listing-title]")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                h_el = item.select_one("h2") or item.select_one("h3")
                if h_el:
                    listing["title"] = h_el.get_text(strip=True)
                    link = h_el.find("a")
                    if link and link.get("href"):
                        listing["url"] = urljoin(self.base_url, link["href"])

            if not listing.get("title") or len(listing["title"]) < 3:
                continue

            # Price (typically USD)
            price_el = (
                item.select_one("span.price")
                or item.select_one("div[class*='price']")
                or item.select_one("span[class*='price']")
            )
            if price_el:
                price_text = price_el.get_text(strip=True)
                listing["price"], listing["currency"] = parse_price_with_currency(price_text)
                if not listing.get("currency"):
                    listing["currency"] = "USD"

            # Location
            loc_el = (
                item.select_one("span.location")
                or item.select_one("div[class*='location']")
                or item.select_one("span[class*='location']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID
            data_id = item.get("id") or item.get("data-listing")
            if data_id:
                listing["id"] = str(data_id).replace("listing-", "")
            elif listing.get("url"):
                listing["id"] = hashlib.md5(listing["url"].encode()).hexdigest()[:16]

            results.append(listing)

        return results

    def _has_next_page(self, html: str) -> bool:
        """Проверить есть ли следующая страница."""
        soup = BeautifulSoup(html, "html.parser")
        return bool(
            soup.select_one("a.next-page")
            or soup.select_one("a[rel='next']")
            or soup.select_one("li.next a")
            or soup.select_one("a[class*='next']")
        )

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency=item.get("currency", "USD"),
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
            ))
        return tenders

    def run(self, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг MachineryTrader."""
        all_items: list[dict] = []
        seen_urls: set[str] = set()

        with self:
            for category in SEARCH_CATEGORIES:
                logger.info(f"[MachineryTrader] Category: {category}")

                for page in range(1, max_pages + 1):
                    try:
                        url = self._build_url(category, page)
                        resp = self.fetch(url)
                        items = self._parse_listing_page(resp.text)

                        if not items:
                            logger.info(f"  Page {page}: no items, stopping")
                            break

                        new_items = []
                        for item in items:
                            item_url = item.get("url", "")
                            if item_url and item_url not in seen_urls:
                                seen_urls.add(item_url)
                                new_items.append(item)

                        all_items.extend(new_items)
                        logger.info(f"  Page {page}: {len(new_items)} new items")

                        if not self._has_next_page(resp.text):
                            break
                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[MachineryTrader] Total: {len(tenders)} listings")
        return tenders
