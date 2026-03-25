"""Парсер Mascus.com — международный маркетплейс б/у спецтехники.

Mascus — Next.js сайт. Данные листингов находятся в __NEXT_DATA__ JSON.
URL: mascus.com/search?manufacturer=caterpillar&category=construction
Поля: brand, model, priceEURO, priceOriginal, locationCity, locationCountryCode, productId
"""

from __future__ import annotations

import json
import logging
import re

from scrapers.base import BaseScraper
from scrapers.cat_base import to_tender
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# Коды стран СНГ (ISO 3166-1 alpha-2)
CIS_COUNTRY_CODES = {"RU", "KZ", "UZ", "BY", "KG", "TJ", "AZ", "AM", "GE", "MD"}

# Маппинг кодов стран → названия
COUNTRY_NAMES = {
    "RU": "Россия", "KZ": "Казахстан", "UZ": "Узбекистан",
    "BY": "Беларусь", "KG": "Кыргызстан", "TJ": "Таджикистан",
    "AZ": "Азербайджан", "AM": "Армения", "GE": "Грузия", "MD": "Молдова",
}


class MascusScraper(BaseScraper):
    """Парсер mascus.com — б/у Caterpillar через __NEXT_DATA__ JSON."""

    platform = "mascus"
    base_url = "https://www.mascus.com"
    min_delay = 3.0
    max_delay = 8.0
    timeout = 45.0

    def _build_search_url(self, page: int = 1) -> str:
        """URL поиска Caterpillar на Mascus."""
        url = f"{self.base_url}/search?manufacturer=caterpillar&category=construction"
        if page > 1:
            url += f"&page={page}"
        return url

    def _extract_json_items(self, html: str) -> tuple[list[dict], int]:
        """Извлечь список товаров из __NEXT_DATA__ JSON.

        Returns:
            (items, totalResults)
        """
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return [], 0

        try:
            data = json.loads(match.group(1))
            search_data = (
                data.get("props", {})
                .get("pageProps", {})
                .get("searchRes", {})
                .get("searchData", {})
            )
            items = search_data.get("items", [])
            total = search_data.get("totalResults", 0)
            return items, total
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"[Mascus] JSON parse error: {e}")
            return [], 0

    def _item_to_dict(self, item: dict) -> dict | None:
        """Конвертировать Mascus JSON item в наш формат."""
        brand = item.get("brand", "")
        model = item.get("model", "")
        if not model:
            return None

        # Фильтр: только Caterpillar (Cat)
        if brand.lower() not in ("caterpillar", "cat"):
            return None

        title = f"{brand} {model}".strip()
        product_id = str(item.get("productId", ""))

        # Price: предпочитаем оригинальную валюту
        price = item.get("priceOriginal") or item.get("priceEURO")
        currency = item.get("priceOriginalUnit", "EUR")
        if not item.get("priceOriginal") and item.get("priceEURO"):
            currency = "EUR"
        # Нормализация валюты
        currency = currency.upper().strip()
        if currency in ("EURO", "€"):
            currency = "EUR"

        # Location
        country_code = (item.get("locationCountryCode") or "").upper()
        city = item.get("locationCity", "")
        location_parts = [p for p in [city, COUNTRY_NAMES.get(country_code, country_code)] if p]
        location = ", ".join(location_parts) if location_parts else None

        # Year + hours для описания
        desc_parts = []
        year = item.get("yearOfManufacture")
        if year:
            desc_parts.append(f"Год: {year}")
        hours = item.get("meterReadout")
        if hours:
            unit = item.get("meterReadoutUnit", "ч")
            desc_parts.append(f"Наработка: {hours} {unit}")
        category = item.get("categoryName")
        if category:
            desc_parts.append(category)

        return {
            "title": title,
            "price": float(price) if price else None,
            "currency": currency,
            "location": location,
            "country_code": country_code,
            "id": product_id,
            "description": ", ".join(desc_parts) if desc_parts else None,
        }

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            url = f"{self.base_url}/product/{item['id']}" if item.get("id") else None
            tenders.append(to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency=item.get("currency", "EUR"),
                region=item.get("location"),
                url=url,
                registry_number=item.get("id"),
                description=item.get("description"),
            ))
        return tenders

    def run(self, max_pages: int = 5, cis_only: bool = False, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг Mascus.

        Args:
            max_pages: макс. страниц (40 items/page)
            cis_only: фильтровать только СНГ (True) или всё (False)
        """
        all_items: list[dict] = []
        seen_ids: set[str] = set()

        with self:
            for page in range(1, max_pages + 1):
                try:
                    url = self._build_search_url(page)
                    logger.info(f"[Mascus] Page {page}: {url}")
                    resp = self.fetch(url)
                    json_items, total = self._extract_json_items(resp.text)

                    if not json_items:
                        logger.info(f"  Page {page}: no items, stopping")
                        break

                    page_count = 0
                    for raw_item in json_items:
                        parsed = self._item_to_dict(raw_item)
                        if not parsed:
                            continue

                        # Filter CIS only
                        if cis_only and parsed.get("country_code") not in CIS_COUNTRY_CODES:
                            continue

                        # Dedup
                        item_id = parsed.get("id", "")
                        if item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)

                        all_items.append(parsed)
                        page_count += 1

                    logger.info(f"  Page {page}: {page_count} CIS items (of {len(json_items)} total)")

                    if len(json_items) < 40:
                        break  # Last page

                except Exception as e:
                    logger.warning(f"  Error page {page}: {e}")
                    break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[Mascus] Total: {len(tenders)} CIS listings")
        return tenders
