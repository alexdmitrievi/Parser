"""Парсер Росатом (zakupki.rosatom.ru).

Корпоративная площадка Росатома — закупки по 223-ФЗ.
Парсит открытый список закупок через HTML или JSON API.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RosatomScraper(BaseScraper):
    """Парсер zakupki.rosatom.ru."""

    platform = "rosatom"
    base_url = "https://zakupki.rosatom.ru"
    min_delay = 3.0
    max_delay = 7.0

    SEARCH_URL = "https://zakupki.rosatom.ru/purchases"
    API_URL = "https://zakupki.rosatom.ru/api/purchases"

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        s = s.strip()[:19]
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", str(text).replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        try:
            v = float(cleaned)
            return v if v > 0 else None
        except ValueError:
            return None

    def _fetch_api(self, query: str, page: int = 1, size: int = 20) -> list[dict]:
        """JSON API запрос."""
        params = {
            "search": query,
            "page": str(page - 1),
            "size": str(size),
            "status": "published",
        }
        try:
            resp = self.fetch(f"{self.API_URL}?{urlencode(params)}")
            data = resp.json()
            return data.get("content", data.get("items", data.get("purchases", [])))
        except Exception:
            return []

    def _fetch_html(self, query: str, page: int = 1) -> list[dict]:
        """HTML-парсинг страницы поиска."""
        params = {"search": query, "page": str(page)}
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        try:
            resp = self.fetch(url)
        except Exception as e:
            logger.warning(f"[Rosatom] Fetch error: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        # Типичная структура: таблица или карточки закупок
        rows = soup.select(
            "table.purchases tbody tr, "
            ".purchase-item, .purchase-card, "
            "div[class*='purchase'], article"
        )

        for row in rows:
            item: dict = {}
            link = row.select_one("a[href*='/purchase'], a[href*='/lot'], h3 a, h2 a, td a")
            if not link:
                continue
            item["title"] = link.get_text(strip=True)
            if not item["title"] or len(item["title"]) < 5:
                continue
            href = link.get("href", "")
            item["url"] = href if href.startswith("http") else self.base_url + href
            num = re.search(r"(\d{6,})", href)
            if num:
                item["registry_number"] = num.group(1)

            # Цена
            price_el = row.select_one(".price, .nmck, .initial-price, [class*='price']")
            if price_el:
                item["nmck"] = self._parse_price(price_el.get_text())

            # Заказчик
            cells = row.find_all("td")
            if len(cells) >= 2:
                for i, cell in enumerate(cells):
                    text = cell.get_text(strip=True)
                    if "Росатом" in text or "РОСАТОМ" in text or ("АО" in text or "ООО" in text or "ГК" in text):
                        if len(text) > 5:
                            item["customer"] = text[:300]
                            break

            customer_el = row.select_one(".customer, .organizer, [class*='customer']")
            if customer_el and not item.get("customer"):
                item["customer"] = customer_el.get_text(strip=True)

            # Дедлайн
            deadline_el = row.select_one(".deadline, .end-date, time, [class*='deadline']")
            if deadline_el:
                item["deadline"] = deadline_el.get("datetime") or deadline_el.get_text(strip=True)
            else:
                date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", row.get_text())
                if date_match:
                    item["deadline"] = date_match.group(1)

            results.append(item)

        return results

    def _api_to_dict(self, purchase: dict) -> Optional[dict]:
        title = (
            purchase.get("purchaseName") or purchase.get("name") or
            purchase.get("subject") or purchase.get("title", "")
        )
        if not title or len(title) < 3:
            return None
        lot_id = str(
            purchase.get("purchaseNumber") or purchase.get("id") or
            purchase.get("registryNumber", "")
        )
        url_path = purchase.get("url") or f"/purchases/{lot_id}"
        url = url_path if url_path.startswith("http") else self.base_url + url_path
        return {
            "title": title,
            "registry_number": lot_id or None,
            "url": url,
            "customer": purchase.get("customerName") or purchase.get("organizer"),
            "nmck": self._parse_price(
                purchase.get("initialPrice") or purchase.get("nmck") or purchase.get("price")
            ),
            "publish_date": self._parse_date(
                purchase.get("publishDate") or purchase.get("publicationDate", "")
            ),
            "deadline": self._parse_date(
                purchase.get("submissionDeadline") or purchase.get("endDate", "")
            ),
            "region": purchase.get("deliveryRegion") or purchase.get("region"),
        }

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            if not item.get("title"):
                continue
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="223-fz",
                title=item["title"],
                customer_name=item.get("customer"),
                customer_region=item.get("region"),
                nmck=item.get("nmck"),
                publish_date=item.get("publish_date") if isinstance(item.get("publish_date"), datetime) else self._parse_date(item.get("publish_date", "")),
                submission_deadline=item.get("deadline") if isinstance(item.get("deadline"), datetime) else self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "строительство", "ремонт", "проектирование",
                "поставка оборудования", "монтаж", "поставка материалов",
                "IT", "транспортные услуги", "охрана",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[Rosatom] Searching: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        raw = self._fetch_api(query, page)
                        if raw:
                            items = [d for d in (self._api_to_dict(r) for r in raw) if d]
                        else:
                            items = self._fetch_html(query, page)

                        if not items:
                            break

                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        logger.info(f"[Rosatom] Total: {len(all_tenders)} tenders")
        return all_tenders
