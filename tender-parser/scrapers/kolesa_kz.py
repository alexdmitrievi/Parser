"""Парсер Kolesa.kz — маркетплейс Казахстана (раздел спецтехники).

Ищет б/у Caterpillar в разделе спецтехники.
Цены в KZT (казахстанский тенге).
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.cat_base import parse_price, to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# URL для поиска спецтехники
BASE_SEARCH_URL = "https://kolesa.kz/spectehnika/"


class KolesaKzScraper(BaseScraper):
    """Парсер kolesa.kz — б/у Caterpillar спецтехника (Казахстан)."""

    platform = "kolesa_kz"
    base_url = "https://kolesa.kz"
    min_delay = 3.0
    max_delay = 6.0
    timeout = 45.0

    def _build_search_url(self, page: int = 1) -> str:
        """URL поиска Caterpillar в разделе спецтехники."""
        params = {"text": "caterpillar"}
        if page > 1:
            params["page"] = str(page)
        return BASE_SEARCH_URL + "?" + urlencode(params)

    def _parse_listing_page(self, html: str) -> list[dict]:
        """Парсить страницу объявлений Kolesa.kz."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Kolesa.kz: типичная структура — карточки объявлений
        items = (
            soup.select("div.a-card")
            or soup.select("div[class*='a-card']")
            or soup.select("div[data-id]")
            or soup.select("div.a-list__item")
            or soup.select("div[class*='listing']")
        )

        if not items:
            # Fallback: любые блоки с data-id
            items = soup.select("[data-id]")

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
                # Try any first link in the card
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
                item.select_one("span.a-card__price")
                or item.select_one("div[class*='price']")
                or item.select_one("span[class*='price']")
                or item.select_one("[class*='cost']")
            )
            if price_el:
                listing["price"] = parse_price(price_el.get_text())

            # Location
            loc_el = (
                item.select_one("span.a-card__param")
                or item.select_one("div[class*='city']")
                or item.select_one("span[class*='location']")
                or item.select_one("[class*='region']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # Description / params
            desc_el = (
                item.select_one("div.a-card__description")
                or item.select_one("p[class*='description']")
            )
            if desc_el:
                listing["description"] = desc_el.get_text(strip=True)

            # ID
            data_id = item.get("data-id") or item.get("id")
            if data_id:
                listing["id"] = str(data_id)
            elif listing.get("url"):
                # Kolesa.kz: URL формат /a/show/NNNN
                m = re.search(r"/(\d+)/?$", listing["url"])
                listing["id"] = m.group(1) if m else hashlib.md5(
                    listing["url"].encode()
                ).hexdigest()[:16]

            results.append(listing)

        return results

    def _has_next_page(self, html: str) -> bool:
        """Проверить наличие следующей страницы."""
        soup = BeautifulSoup(html, "html.parser")
        return bool(
            soup.select_one("a.next")
            or soup.select_one("a[rel='next']")
            or soup.select_one("[class*='pager'] a[class*='next']")
            or soup.select_one("a[class*='pagination__next']")
        )

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency="KZT",
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
                description=item.get("description"),
            ))
        return tenders

    def run(self, max_pages: int = 5, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг Kolesa.kz (спецтехника CAT)."""
        all_items: list[dict] = []

        with self:
            logger.info("[Kolesa.kz] Searching Caterpillar in spectehnika")

            for page in range(1, max_pages + 1):
                try:
                    url = self._build_search_url(page)
                    resp = self.fetch(url)
                    items = self._parse_listing_page(resp.text)

                    if not items:
                        logger.info(f"  Page {page}: no items, stopping")
                        break

                    all_items.extend(items)
                    logger.info(f"  Page {page}: {len(items)} items")

                    if not self._has_next_page(resp.text):
                        break
                except Exception as e:
                    logger.warning(f"  Error page {page}: {e}")
                    break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[Kolesa.kz] Total: {len(tenders)} listings")
        return tenders
