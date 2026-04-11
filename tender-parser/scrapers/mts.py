"""Парсер МТС (tenders.mts.ru).

Корпоративная площадка закупок ПАО «МТС».
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


class MtsScraper(BaseScraper):
    """Парсер tenders.mts.ru."""

    platform = "mts"
    base_url = "https://tenders.mts.ru"
    min_delay = 3.0
    max_delay = 7.0

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y"]:
            try:
                return datetime.strptime(s.strip()[:16], fmt)
            except ValueError:
                continue
        return None

    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        blocks = soup.select(
            ".purchase-row, .purchase-item, .search-result, "
            "tr[data-id], .lot-card, .tender-item, article, "
            "[class*='purchase'], [class*='tender'], [class*='lot']"
        )

        for block in blocks:
            item = {}
            link = block.select_one(
                "a[href*='/purchase'], a[href*='/tender'], a[href*='/lot'], "
                "a.purchase-link, h3 a, h2 a, a.title"
            )
            if not link:
                continue
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            item["title"] = title
            href = link.get("href", "")
            item["url"] = self.base_url + href if href.startswith("/") else href

            num_match = re.search(r"(\d{6,})", link.get_text() + href)
            if num_match:
                item["registry_number"] = num_match.group(1)

            price_el = block.select_one(".price, .sum, .nmck, .cost")
            if price_el:
                item["nmck"] = self._parse_price(price_el.get_text())

            customer_el = block.select_one(".customer, .organizer, .org-name, .company")
            if customer_el:
                item["customer"] = customer_el.get_text(strip=True)

            date_el = block.select_one(".deadline, .end-date, .date-end, time")
            if date_el:
                item["deadline"] = date_el.get_text(strip=True)

            results.append(item)

        if not results:
            for a in soup.select("a[href*='/purchase'], a[href*='/tender']"):
                t = a.get_text(strip=True)
                if not t or len(t) < 10:
                    continue
                href = a.get("href", "")
                full_url = self.base_url + href if href.startswith("/") else href
                results.append({
                    "title": t,
                    "registry_number": href.rstrip("/").split("/")[-1] if href else t[:40],
                    "url": full_url,
                })

        return results[:80]

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        return [
            TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="223-fz",
                title=item["title"],
                customer_name=item.get("customer"),
                nmck=item.get("nmck"),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            )
            for item in raw_items if item.get("title")
        ]

    def run(self, queries: list[str] | None = None, max_pages: int = 2, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "поставка оборудования", "ремонт", "строительство",
                "IT услуги", "телекоммуникации", "техническое обслуживание",
            ]

        all_tenders: list[TenderCreate] = []
        with self:
            for query in queries:
                logger.info(f"[MTS] Searching: {query}")
                for page in range(1, max_pages + 1):
                    try:
                        url = f"{self.base_url}/search?{urlencode({'q': query, 'page': str(page)})}"
                        resp = self.fetch(url)
                        items = self._parse_page(resp.text)
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[MTS] Total: {len(all_tenders)} tenders")
        return all_tenders
