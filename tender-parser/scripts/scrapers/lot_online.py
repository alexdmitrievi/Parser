"""lot-online.ru — РАД (44-ФЗ, приватизация)."""

from __future__ import annotations

import re
from typing import Any

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text


class LotOnlineScraper(BaseScraper):
    source_platform = "lot_online"
    law_type = "44-fz"
    _base = "https://www.lot-online.ru"

    def listing_url(self) -> str:
        return f"{self._base}/"

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        for row in doc.select("tr, .lot, .auction, .item, [data-lot]"):
            a = row.select_one("a[href*='/auction'], a[href*='/lot'], a[href*='/procedure']")
            if not a:
                continue
            title = text(a)
            if not title or len(title) < 8:
                continue
            href = abs_url(self._base, str(a.get("href", "")))
            num = re.search(r"№\s*([\d\-/]+)", row.get_text(" ", strip=True))
            price_txt = text(row.select_one(".price, .start-price, .nmck"))
            customer = text(row.select_one(".organizer, .seller, .customer"))
            deadline = text(row.select_one(".date-end, .deadline, time"))
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
            for a in doc.select("a[href*='/auction'], a[href*='/lot']"):
                t = text(a)
                if not t or len(t) < 10:
                    continue
                href = abs_url(self._base, str(a.get("href", "")))
                items.append(
                    {
                        "title": t,
                        "registry_number": href.rstrip("/").split("/")[-1],
                        "external_url": href,
                    }
                )
        return items[:80]
