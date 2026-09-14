"""zakupki.mos.ru — региональный портал закупок Москвы."""

from __future__ import annotations

import re
from typing import Any

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text


class ZakupkiMosScraper(BaseScraper):
    source_platform = "zakupki_mos"
    law_type = "regional"
    _base = "https://zakupki.mos.ru"

    def listing_url(self) -> str:
        return f"{self._base}/purchase/list"

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        for row in doc.select("tr, .purchase-card, .card, [class*='Purchase']"):
            a = row.select_one("a[href*='/purchase/'], a[href*='/epz/']")
            if not a:
                continue
            title = text(a)
            if not title or len(title) < 8:
                continue
            href = abs_url(self._base, str(a.get("href", "")))
            num = re.search(r"№\s*([\d\-/]+)", row.get_text(" ", strip=True))
            if not num:
                num = re.search(r"\b(\d{10,})\b", row.get_text(" ", strip=True))
            price_txt = text(row.select_one(".price, .nmck, .sum"))
            customer = text(row.select_one(".customer, .organizer, .organization"))
            deadline = text(row.select_one(".date, .deadline, time"))
            items.append(
                {
                    "title": title,
                    "nmck": parse_price(price_txt),
                    "customer_name": customer,
                    "submission_deadline_raw": deadline,
                    "registry_number": (num.group(1) if num else href.split("/")[-1]),
                    "external_url": href,
                    "customer_region": "Москва",
                }
            )
        if not items:
            for a in doc.select("a[href*='/purchase/']"):
                t = text(a)
                if not t or len(t) < 10:
                    continue
                href = abs_url(self._base, str(a.get("href", "")))
                items.append(
                    {
                        "title": t,
                        "registry_number": href.rstrip("/").split("/")[-1],
                        "external_url": href,
                        "customer_region": "Москва",
                    }
                )
        return items[:100]
