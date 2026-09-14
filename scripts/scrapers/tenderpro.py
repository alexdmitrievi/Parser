"""tenderpro.ru — коммерческая площадка."""

from __future__ import annotations

import re
from typing import Any

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text


class TenderproScraper(BaseScraper):
    source_platform = "tenderpro"
    law_type = "commercial"
    _base = "https://www.tenderpro.ru"

    def listing_url(self) -> str:
        return f"{self._base}/tenders"

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        for row in doc.select("tr, .tender-item, .lot, .card"):
            a = row.select_one("a[href*='/tender'], a[href*='/tenders/']")
            if not a:
                continue
            title = text(a)
            if not title or len(title) < 8:
                continue
            href = abs_url(self._base, str(a.get("href", "")))
            num = re.search(r"№\s*([\w\-/]+)", row.get_text(" ", strip=True))
            price_txt = text(row.select_one(".price, .sum, .nmck"))
            customer = text(row.select_one(".customer, .org"))
            deadline = text(row.select_one(".date, .deadline, time"))
            items.append(
                {
                    "title": title,
                    "nmck": parse_price(price_txt),
                    "customer_name": customer,
                    "submission_deadline_raw": deadline,
                    "registry_number": (num.group(1) if num else href.split("/")[-1]),
                    "external_url": href,
                }
            )
        if not items:
            for a in doc.select("a[href*='/tender']"):
                t = text(a)
                if not t or len(t) < 10:
                    continue
                href = abs_url(self._base, str(a.get("href", "")))
                items.append(
                    {
                        "title": t,
                        "registry_number": href.split("/")[-1],
                        "external_url": href,
                    }
                )
        return items[:80]
