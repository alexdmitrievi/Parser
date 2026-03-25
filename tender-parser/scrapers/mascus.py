"""Парсер Mascus.com — международный маркетплейс б/у спецтехники.

Ищет Caterpillar по странам СНГ (Россия, Казахстан, Узбекистан и т.д.).
URL: mascus.com/construction-equipment/used-caterpillar
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.cat_base import parse_price_with_currency, to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# Страны СНГ на Mascus
CIS_COUNTRIES = ["Russia", "Kazakhstan", "Uzbekistan", "Belarus", "Kyrgyzstan"]

# Категории техники
CATEGORIES = [
    "construction-equipment",
    "mining-equipment",
    "material-handling-equipment",
]


class MascusScraper(BaseScraper):
    """Парсер mascus.com — б/у Caterpillar (СНГ)."""

    platform = "mascus"
    base_url = "https://www.mascus.com"
    min_delay = 3.0
    max_delay = 8.0
    timeout = 45.0

    def _build_search_url(self, category: str, country: str, page: int = 1) -> str:
        """Построить URL поиска."""
        url = f"{self.base_url}/{category}/used-caterpillar"
        params = []
        if country:
            params.append(f"country={country}")
        if page > 1:
            params.append(f"page={page}")
        if params:
            url += "?" + "&".join(params)
        return url

    def _parse_listing_page(self, html: str) -> list[dict]:
        """Парсить страницу со списком объявлений."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Mascus: listings in <li> or <div> with class containing "listing"
        # Try multiple selectors for robustness
        items = (
            soup.select("div.listing-item")
            or soup.select("li.listing-item")
            or soup.select("div[class*='listing']")
            or soup.select("div.si-listing")
            or soup.select("ul.listing-results li")
        )

        if not items:
            # Fallback: look for structured data or product cards
            items = soup.select("div[data-listing-id]") or soup.select("article")

        for item in items:
            listing: dict = {}

            # Title: usually in <a> or <h2> inside the listing
            title_el = (
                item.select_one("a.listing-title")
                or item.select_one("h2 a")
                or item.select_one("h3 a")
                or item.select_one("a[class*='title']")
                or item.select_one(".listing-name a")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                # Try just finding any meaningful title
                title_tag = item.select_one("h2") or item.select_one("h3")
                if title_tag:
                    listing["title"] = title_tag.get_text(strip=True)

            if not listing.get("title") or len(listing["title"]) < 3:
                continue

            # Price
            price_el = (
                item.select_one("span.listing-price")
                or item.select_one("div[class*='price']")
                or item.select_one("span[class*='price']")
                or item.select_one(".price")
            )
            if price_el:
                price_text = price_el.get_text(strip=True)
                listing["price"], listing["currency"] = parse_price_with_currency(price_text)

            # Location
            loc_el = (
                item.select_one("span.listing-location")
                or item.select_one("div[class*='location']")
                or item.select_one("span[class*='location']")
                or item.select_one(".location")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID for dedup
            data_id = item.get("data-listing-id") or item.get("data-id")
            if data_id:
                listing["id"] = str(data_id)
            elif listing.get("url"):
                listing["id"] = hashlib.md5(listing["url"].encode()).hexdigest()[:16]

            results.append(listing)

        return results

    def _has_next_page(self, html: str) -> bool:
        """Проверить наличие следующей страницы."""
        soup = BeautifulSoup(html, "html.parser")
        next_link = (
            soup.select_one("a.next")
            or soup.select_one("a[rel='next']")
            or soup.select_one("li.next a")
            or soup.select_one("a[class*='next']")
        )
        return next_link is not None

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        """Конвертировать сырые данные в TenderCreate."""
        tenders = []
        for item in raw_items:
            tenders.append(to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency=item.get("currency", "EUR"),
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
            ))
        return tenders

    def run(self, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг Mascus по странам СНГ."""
        all_items: list[dict] = []
        seen_urls: set[str] = set()

        with self:
            for country in CIS_COUNTRIES:
                for category in CATEGORIES:
                    logger.info(f"[Mascus] {category} / {country}")

                    for page in range(1, max_pages + 1):
                        try:
                            url = self._build_search_url(category, country, page)
                            resp = self.fetch(url)
                            items = self._parse_listing_page(resp.text)

                            if not items:
                                logger.info(f"  Page {page}: no items, stopping")
                                break

                            # Dedup by URL
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
        logger.info(f"[Mascus] Total: {len(tenders)} listings")
        return tenders
