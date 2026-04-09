"""Парсер СберB2B (sberb2b.ru).

Корпоративная площадка Сбербанка для закупок по 223-ФЗ и коммерческих.
Парсит REST API /api/v1/lots/search (JSON).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SberB2BScraper(BaseScraper):
    """Парсер sberb2b.ru — корпоративная площадка Сбербанка."""

    platform = "sberb2b"
    base_url = "https://sberb2b.ru"
    min_delay = 3.0
    max_delay = 7.0

    # Публичный REST API (без авторизации для открытых лотов)
    API_URL = "https://sberb2b.ru/api/v1/lots/search"
    SEARCH_URL = "https://sberb2b.ru/lots"

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        s = s[:19].strip()
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    def _parse_price(self, val) -> Optional[float]:
        if val is None:
            return None
        try:
            v = float(str(val).replace(" ", "").replace(",", "."))
            return v if v > 0 else None
        except (ValueError, TypeError):
            return None

    def _fetch_api(self, query: str, page: int = 1, page_size: int = 20) -> list[dict]:
        """Запрос к JSON API площадки."""
        payload = {
            "query": query,
            "page": page - 1,  # 0-indexed
            "size": page_size,
            "status": "ACTIVE",
        }
        try:
            resp = self.post(self.API_URL, json=payload)
            data = resp.json()
            # Ответ: {"content": [...], "totalElements": N}
            return data.get("content", data.get("lots", data.get("items", [])))
        except Exception:
            return []

    def _fetch_html(self, query: str, page: int = 1) -> list[dict]:
        """Fallback: HTML-парсинг страницы поиска."""
        from bs4 import BeautifulSoup
        params = {"search": query, "page": str(page), "status": "active"}
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        try:
            resp = self.fetch(url)
        except Exception as e:
            logger.warning(f"[SberB2B] HTML fetch error: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        # Карточки лотов — несколько возможных селекторов
        cards = soup.select(
            ".lot-card, .lot-item, .tender-card, article.card, "
            "div[class*='lot'], div[class*='tender']"
        )
        for card in cards:
            item: dict = {}
            link = card.select_one("a[href*='/lot'], a[href*='/tender'], h2 a, h3 a, .title a")
            if not link:
                continue
            item["title"] = link.get_text(strip=True)
            if not item["title"] or len(item["title"]) < 5:
                continue
            href = link.get("href", "")
            item["url"] = href if href.startswith("http") else self.base_url + href
            # Номер из URL или текста
            num = re.search(r"(\d{6,})", href)
            if num:
                item["registry_number"] = num.group(1)

            price_el = card.select_one(".price, .nmck, .sum, [class*='price'], [class*='amount']")
            if price_el:
                item["nmck"] = self._parse_price(
                    re.sub(r"[^\d.,]", "", price_el.get_text().replace(" ", "").replace(",", "."))
                )

            customer_el = card.select_one(".customer, .organizer, [class*='customer'], [class*='organizer']")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)

            deadline_el = card.select_one(".deadline, .end-date, time, [class*='deadline'], [class*='date']")
            if deadline_el:
                item["deadline"] = deadline_el.get("datetime") or deadline_el.get_text(strip=True)

            results.append(item)

        return results

    def _api_to_dict(self, lot: dict) -> Optional[dict]:
        """Преобразовать JSON-объект лота в плоский dict."""
        title = (
            lot.get("lotName") or lot.get("name") or lot.get("title") or
            lot.get("subject") or lot.get("purchaseName", "")
        )
        if not title or len(title) < 3:
            return None

        lot_id = str(
            lot.get("lotId") or lot.get("id") or lot.get("number") or
            lot.get("registryNumber", "")
        )
        url_path = lot.get("url") or f"/lots/{lot_id}" if lot_id else ""
        url = url_path if url_path.startswith("http") else self.base_url + url_path

        return {
            "title": title,
            "registry_number": lot_id or None,
            "url": url,
            "customer": (
                lot.get("customerName") or lot.get("customer", {}).get("name")
                if isinstance(lot.get("customer"), dict) else lot.get("customer")
            ),
            "nmck": self._parse_price(
                lot.get("initialPrice") or lot.get("nmck") or lot.get("price") or
                lot.get("startPrice")
            ),
            "publish_date": self._parse_date(
                lot.get("publishDate") or lot.get("createdAt") or lot.get("publicationDate", "")
            ),
            "deadline": self._parse_date(
                lot.get("endDate") or lot.get("deadline") or lot.get("submissionDeadline", "")
            ),
            "region": lot.get("region") or lot.get("deliveryRegion") or lot.get("deliveryPlace"),
            "law_type": "223-fz" if "223" in str(lot.get("lawType", "")) else "commercial",
        }

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            if not item.get("title"):
                continue
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type=item.get("law_type", "commercial"),
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
                "строительство", "ремонт", "поставка оборудования",
                "IT", "транспортные услуги", "мебель",
                "поставка продуктов", "охрана", "клининг",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[SberB2B] Searching: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        # Пробуем API
                        raw = self._fetch_api(query, page)
                        if raw:
                            items = [d for d in (self._api_to_dict(r) for r in raw) if d]
                        else:
                            # Fallback на HTML
                            items = self._fetch_html(query, page)

                        if not items:
                            break

                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        logger.info(f"[SberB2B] Total: {len(all_tenders)} tenders")
        return all_tenders
