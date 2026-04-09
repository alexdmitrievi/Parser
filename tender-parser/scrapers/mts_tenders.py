"""Парсер МТС (tenders.mts.ru).

Корпоративный портал закупок МТС (223-ФЗ и коммерческие).
URL: tenders.mts.ru
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


class MtsTendersScraper(BaseScraper):
    """Парсер tenders.mts.ru."""

    platform = "mts_tenders"
    base_url = "https://tenders.mts.ru"
    min_delay = 3.0
    max_delay = 8.0

    SEARCH_URL = "https://tenders.mts.ru/tenders"
    API_URL = "https://tenders.mts.ru/api/v1/tenders"

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        s = str(s).strip()[:19]
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    def _parse_price(self, text) -> Optional[float]:
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
        params = {"query": query, "page": str(page), "size": str(size), "status": "ACTIVE"}
        try:
            resp = self.fetch(f"{self.API_URL}?{urlencode(params)}")
            data = resp.json()
            return data.get("items", data.get("content", data.get("tenders", [])))
        except Exception:
            return []

    def _fetch_html(self, query: str, page: int = 1) -> list[dict]:
        params = {"search": query, "page": str(page)}
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        try:
            resp = self.fetch(url)
        except Exception as e:
            logger.warning(f"[MTS] Fetch error: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        rows = soup.select(
            "table tbody tr, "
            ".tender-item, .tender-card, "
            "div[class*='tender'], article, li[class*='tender']"
        )

        for row in rows:
            item: dict = {}
            link = row.select_one("a[href*='tender'], a[href*='lot'], h2 a, h3 a, .subject a, td a")
            if not link:
                continue
            item["title"] = link.get_text(strip=True)
            if not item["title"] or len(item["title"]) < 5:
                continue
            href = link.get("href", "")
            item["url"] = href if href.startswith("http") else self.base_url + href
            num = re.search(r"(\d{5,})", href)
            if num:
                item["registry_number"] = num.group(1)

            price_el = row.select_one(".price, .nmck, [class*='price'], [class*='amount']")
            if price_el:
                item["nmck"] = self._parse_price(price_el.get_text())

            customer_el = row.select_one(".customer, .organizer, [class*='customer']")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)[:300]

            deadline_el = row.select_one(".deadline, .end-date, time, [class*='deadline']")
            if deadline_el:
                item["deadline"] = deadline_el.get("datetime") or deadline_el.get_text(strip=True)
            else:
                date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", row.get_text())
                if date_match:
                    item["deadline"] = date_match.group(1)

            results.append(item)

        return results

    def _api_to_dict(self, tender: dict) -> Optional[dict]:
        title = (
            tender.get("tenderName") or tender.get("name") or
            tender.get("subject") or tender.get("title", "")
        )
        if not title or len(title) < 3:
            return None
        tender_id = str(tender.get("tenderNumber") or tender.get("id") or tender.get("number", ""))
        url_path = tender.get("url") or f"/tenders/{tender_id}"
        url = url_path if url_path.startswith("http") else self.base_url + url_path
        return {
            "title": title,
            "registry_number": tender_id or None,
            "url": url,
            "customer": tender.get("customerName") or tender.get("organizer"),
            "nmck": self._parse_price(
                tender.get("startPrice") or tender.get("initialPrice") or tender.get("nmck")
            ),
            "publish_date": self._parse_date(
                tender.get("publishDate") or tender.get("publicationDate", "")
            ),
            "deadline": self._parse_date(
                tender.get("submissionDeadline") or tender.get("endDate", "")
            ),
            "region": tender.get("region") or tender.get("deliveryRegion"),
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
                "строительство", "ремонт", "IT оборудование",
                "телекоммуникации", "сетевое оборудование",
                "транспортные услуги", "поставка оборудования",
                "охрана", "клининг", "программное обеспечение",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[MTS] Searching: {query}")
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

        logger.info(f"[MTS] Total: {len(all_tenders)} tenders")
        return all_tenders
