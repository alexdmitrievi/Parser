"""Парсер РАД / lot-online.ru (Российский Аукционный Дом).

Аукционы банкротов: земля, недвижимость, транспорт, оборудование.
Использует AJAX API: dispatch=categories.view&is_ajax=1
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Категории РАД → property_type tag
CATEGORIES = {
    2: ("Земельные участки", "land"),
    17: ("Коммерческая недвижимость", "real_estate"),
    3: ("Жилая недвижимость", "real_estate"),
    4: ("Транспорт", "vehicles"),
    5: ("Оборудование", "equipment"),
    6: ("Прочее имущество", "other_assets"),
    7: ("Коллекционные предметы и драгоценности", "other_assets"),
}


class LotOnlineScraper(BaseScraper):
    """Парсер catalog.lot-online.ru — аукционы банкротов."""

    platform = "lot_online"
    base_url = "https://catalog.lot-online.ru"
    min_delay = 2.0
    max_delay = 5.0

    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", ".").replace("\xa0", "").replace(" ", ""))
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    def _fetch_category_page(self, category_id: int, page: int = 1) -> str:
        """Получить HTML лотов через AJAX API."""
        url = (
            f"{self.base_url}/index.php?dispatch=categories.view"
            f"&category_id={category_id}"
            f"&page={page}"
            f"&is_ajax=1&result_ids=pagination_contents"
        )
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        resp = self.fetch(url, headers=headers)
        data = resp.json()
        return data.get("html", {}).get("pagination_contents", "")

    def _parse_lots(self, html: str, category_name: str, property_type: str) -> list[dict]:
        """Парсить HTML с лотами."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        items = soup.select("div.ty-grid-list__item")
        for item in items:
            lot = {}

            # Название + ссылка
            title_el = item.select_one("a.product-title")
            if title_el:
                lot["title"] = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                lot["url"] = href if href.startswith("http") else self.base_url + href
            else:
                name_el = item.select_one("div.ty-grid-list__item-name")
                if name_el:
                    lot["title"] = name_el.get_text(strip=True)

            if not lot.get("title") or len(lot["title"]) < 5:
                continue

            # Цена
            price_el = item.select_one("span.ty-price-num")
            if price_el:
                lot["price"] = self._parse_price(price_el.get_text())

            # Номер лота
            code_el = item.select_one("span.ty-grid-list__product-code")
            if code_el:
                lot["code"] = code_el.get_text(strip=True)

            lot["category"] = category_name
            lot["property_type"] = property_type

            results.append(lot)

        return results

    def _enrich_region(self, url: str) -> Optional[str]:
        """Дозагрузить регион с детальной страницы лота (через dt/dd пары)."""
        try:
            resp = self.fetch(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Ищем dt/dd пару: <dt>Регион</dt><dd>Московская обл</dd>
            for dt in soup.find_all("dt"):
                label = dt.get_text(strip=True).lower()
                if label in ("регион", "местонахождение", "субъект"):
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        val = dd.get_text(strip=True)
                        if val and len(val) >= 3:
                            return val
            # Fallback: ищем "Адрес" для извлечения региона
            for dt in soup.find_all("dt"):
                label = dt.get_text(strip=True).lower()
                if "адрес" in label:
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        val = dd.get_text(strip=True)
                        if val and len(val) >= 5:
                            # Извлекаем первую часть адреса (обычно регион)
                            parts = val.split(",")
                            return parts[0].strip() if parts else val[:60]
        except Exception:
            pass
        return None

    def _enrich_lots(self, items: list[dict], max_enrich: int = 50) -> list[dict]:
        """Дозагрузить регионы с детальных страниц."""
        enriched = 0
        for item in items:
            if enriched >= max_enrich:
                break
            if item.get("region") or not item.get("url"):
                continue
            self._delay()
            region = self._enrich_region(item["url"])
            if region:
                item["region"] = region
                enriched += 1
        logger.info(f"[РАД] Enriched {enriched} lots with region data")
        return items

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            code = item.get("code", "")
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=code or None,
                law_type="auction",
                title=item["title"],
                description=item.get("category", ""),
                customer_name=None,
                customer_region=item.get("region"),
                nmck=item.get("price"),
                original_url=item.get("url", ""),
                niche_tags=[item.get("property_type", "other_assets")],
            ))
        return tenders

    def run(self, categories: dict | None = None, max_pages: int = 5, **kwargs) -> list[TenderCreate]:
        if categories is None:
            categories = CATEGORIES

        all_items: list[dict] = []

        with self:
            for cat_id, (cat_name, prop_type) in categories.items():
                logger.info(f"[РАД] Category: {cat_name} (id={cat_id})")

                for page in range(1, max_pages + 1):
                    try:
                        self._delay()
                        html = self._fetch_category_page(cat_id, page)
                        lots = self._parse_lots(html, cat_name, prop_type)
                        if not lots:
                            logger.info(f"  Page {page}: no lots, stopping")
                            break
                        all_items.extend(lots)
                        logger.info(f"  Page {page}: {len(lots)} lots")
                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        # Дозагрузка регионов
        if all_items:
            all_items = self._enrich_lots(all_items, max_enrich=50)

        tenders = self.parse_tenders(all_items)
        logger.info(f"[РАД] Total: {len(tenders)} lots")
        return tenders
