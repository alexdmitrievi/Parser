"""Парсер Avito.ru — б/у спецтехника Caterpillar (Россия).

Поиск по категории «Спецтехника» с ключевым словом Caterpillar.
Avito имеет агрессивную антибот-защиту — используем увеличенные задержки
и правильные заголовки. При блокировке — graceful degradation.
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

# Поисковые запросы
SEARCH_QUERIES = [
    "caterpillar",
    "CAT экскаватор",
    "CAT бульдозер",
    "CAT погрузчик",
]

# Базовый URL для спецтехники
BASE_SEARCH_URL = "https://www.avito.ru/rossiya/gruzoviki_i_spetstekhnika/spectehnika-ASg"


class AvitoCatScraper(BaseScraper):
    """Парсер Avito.ru — б/у Caterpillar спецтехника."""

    platform = "avito_cat"
    base_url = "https://www.avito.ru"
    min_delay = 5.0
    max_delay = 12.0
    timeout = 45.0

    def _build_headers(self) -> dict[str, str]:
        """Заголовки для Avito — усиленная маскировка."""
        headers = super()._build_headers()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/",
        })
        return headers

    def _build_search_url(self, query: str, page: int = 1) -> str:
        """URL поиска спецтехники."""
        params = {"q": query}
        if page > 1:
            params["p"] = str(page)
        return BASE_SEARCH_URL + "?" + urlencode(params)

    def _parse_listing_page(self, html: str) -> list[dict]:
        """Парсить страницу объявлений Avito."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Avito: items are typically in divs with data-marker="item"
        items = (
            soup.select("[data-marker='item']")
            or soup.select("div[class*='iva-item']")
            or soup.select("div[itemtype='http://schema.org/Product']")
            or soup.select("div[class*='items-item']")
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
                # Title может быть в тексте элемента или в его дочернем span
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

            # Фильтр: оставляем только CAT/Caterpillar
            title_lower = listing["title"].lower()
            if not any(kw in title_lower for kw in ("cat", "caterpillar", "катерпиллер", "катерпиллар")):
                continue

            # Price (RUB)
            price_el = (
                item.select_one("[data-marker='item-price']")
                or item.select_one("[itemprop='price']")
                or item.select_one("span[class*='price']")
                or item.select_one("[class*='price']")
            )
            if price_el:
                # Avito: price может быть в атрибуте content или в тексте
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
                or item.select_one("span[class*='location']")
                or item.select_one("[class*='address']")
            )
            if loc_el:
                listing["location"] = loc_el.get_text(strip=True)

            # ID from data-item-id or URL
            data_id = item.get("data-item-id") or item.get("id")
            if data_id:
                listing["id"] = str(data_id)
            elif listing.get("url"):
                # Извлекаем ID из URL: /moskva/.../_1234567890
                m = re.search(r"_(\d+)$", listing["url"])
                listing["id"] = m.group(1) if m else hashlib.md5(
                    listing["url"].encode()
                ).hexdigest()[:16]

            results.append(listing)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(to_tender(
                platform=self.platform,
                title=item["title"],
                price=item.get("price"),
                currency="RUB",
                region=item.get("location"),
                url=item.get("url"),
                registry_number=item.get("id"),
            ))
        return tenders

    def run(self, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг Avito (спецтехника CAT)."""
        all_items: list[dict] = []
        seen_ids: set[str] = set()

        with self:
            for query in SEARCH_QUERIES:
                logger.info(f"[Avito] Query: {query}")

                for page in range(1, max_pages + 1):
                    try:
                        url = self._build_search_url(query, page)
                        resp = self.fetch(url)

                        # Проверка на антибот
                        if resp.status_code == 403 or "captcha" in resp.text.lower():
                            logger.warning(f"[Avito] Blocked (captcha/403), stopping query '{query}'")
                            break

                        items = self._parse_listing_page(resp.text)

                        if not items:
                            logger.info(f"  Page {page}: no items, stopping")
                            break

                        # Dedup
                        new_items = []
                        for item in items:
                            item_id = item.get("id", "")
                            if item_id and item_id not in seen_ids:
                                seen_ids.add(item_id)
                                new_items.append(item)

                        all_items.extend(new_items)
                        logger.info(f"  Page {page}: {len(new_items)} new items")

                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        tenders = self.parse_tenders(all_items)
        logger.info(f"[Avito] Total: {len(tenders)} listings")
        return tenders
