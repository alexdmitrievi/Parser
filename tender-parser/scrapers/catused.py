"""Парсер catused.cat.com — официальный портал б/у техники Caterpillar.

Сайт использует API для загрузки объявлений. Попытаемся использовать
JSON API, а при неудаче — стандартный HTML-парсинг.
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

# Эндпоинты для поиска
SEARCH_API_URL = "https://catused.cat.com/api/equipment"
SEARCH_HTML_URL = "https://catused.cat.com/en/equipment"


class CatUsedScraper(BaseScraper):
    """Парсер catused.cat.com — официальный портал б/у техники CAT."""

    platform = "catused"
    base_url = "https://catused.cat.com"
    min_delay = 3.0
    max_delay = 6.0
    timeout = 45.0

    def _try_api(self, page: int = 1, per_page: int = 50) -> Optional[list[dict]]:
        """Попытаться получить данные через JSON API."""
        try:
            url = SEARCH_API_URL
            params = {
                "manufacturer": "Caterpillar",
                "page": str(page),
                "pageSize": str(per_page),
                "sortBy": "price",
            }
            headers = {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            }
            resp = self.fetch(url, params=params, headers=headers)
            data = resp.json()

            # Возможные форматы ответа API
            items = data if isinstance(data, list) else data.get("items") or data.get("results") or data.get("data") or []
            if not items:
                return None

            results = []
            for item in items:
                listing = {
                    "title": item.get("title") or item.get("name") or item.get("model", ""),
                    "price": item.get("price") or item.get("askingPrice"),
                    "currency": item.get("currency", "USD"),
                    "location": item.get("location") or item.get("dealerLocation") or item.get("country", ""),
                    "url": item.get("url") or item.get("detailUrl", ""),
                    "id": str(item.get("id") or item.get("serialNumber") or ""),
                    "hours": item.get("hours") or item.get("meterReading"),
                    "year": item.get("year") or item.get("yearManufactured"),
                }
                if listing["url"] and not listing["url"].startswith("http"):
                    listing["url"] = urljoin(self.base_url, listing["url"])
                if listing["title"]:
                    results.append(listing)

            return results

        except Exception as e:
            logger.info(f"[CAT Used] API not available: {e}")
            return None

    def _parse_html_page(self, html: str) -> list[dict]:
        """Парсить HTML-страницу со списком техники."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Ищем карточки оборудования
        items = (
            soup.select("div.equipment-card")
            or soup.select("div[class*='equipment']")
            or soup.select("div[class*='product-card']")
            or soup.select("div.card")
            or soup.select("div[class*='listing']")
            or soup.select("article")
        )

        for item in items:
            listing: dict = {}

            # Title
            title_el = (
                item.select_one("h2 a")
                or item.select_one("h3 a")
                or item.select_one("a[class*='title']")
                or item.select_one(".equipment-title")
                or item.select_one("a[class*='name']")
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                listing["url"] = urljoin(self.base_url, href) if href else ""
            else:
                h_tag = item.select_one("h2") or item.select_one("h3")
                if h_tag:
                    listing["title"] = h_tag.get_text(strip=True)

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

            # Location
            loc_el = (
                item.select_one("[class*='location']")
                or item.select_one("[class*='dealer']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID
            data_id = item.get("data-id") or item.get("data-equipment-id")
            listing["id"] = str(data_id) if data_id else hashlib.md5(
                (listing.get("url") or listing["title"]).encode()
            ).hexdigest()[:16]

            results.append(listing)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            # Формируем описание с доп. информацией
            desc_parts = []
            if item.get("year"):
                desc_parts.append(f"Год: {item['year']}")
            if item.get("hours"):
                desc_parts.append(f"Часы: {item['hours']}")

            tenders.append(to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency=item.get("currency", "USD"),
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
                description=", ".join(desc_parts) if desc_parts else None,
            ))
        return tenders

    def run(self, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг CAT Used."""
        all_items: list[dict] = []

        with self:
            # Сначала пробуем API
            for page in range(1, max_pages + 1):
                api_items = self._try_api(page=page)
                if api_items is None:
                    if page == 1:
                        logger.info("[CAT Used] API failed, falling back to HTML")
                    break
                all_items.extend(api_items)
                logger.info(f"[CAT Used] API page {page}: {len(api_items)} items")
                if len(api_items) < 50:
                    break

            # Если API не сработал — парсим HTML
            if not all_items:
                for page in range(1, max_pages + 1):
                    try:
                        url = SEARCH_HTML_URL
                        if page > 1:
                            url += f"?page={page}"
                        resp = self.fetch(url)
                        items = self._parse_html_page(resp.text)

                        if not items:
                            logger.info(f"  HTML page {page}: no items, stopping")
                            break

                        all_items.extend(items)
                        logger.info(f"  HTML page {page}: {len(items)} items")
                    except Exception as e:
                        logger.warning(f"  Error HTML page {page}: {e}")
                        break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[CAT Used] Total: {len(tenders)} listings")
        return tenders
