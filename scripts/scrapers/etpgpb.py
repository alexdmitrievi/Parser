"""etpgpb.ru — ЭТП ГПБ (223-ФЗ)."""

from __future__ import annotations

import re
from typing import Any

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text


class EtpgpbScraper(BaseScraper):
    source_platform = "etpgpb"
    law_type = "223-fz"
    _base = "https://etpgpb.ru"

    def listing_url(self) -> str:
        return f"{self._base}/procedures/"

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        for row in doc.select("tr, .procedure, .lot, .card, [class*='procedure']"):
            link_el = row.select_one("a[href*='/procedure'], a[href*='/procedures/']")
            if not link_el:
                continue
            title = text(link_el)
            if not title or len(title) < 8:
                continue
            href = abs_url(self._base, str(link_el.get("href", "")))
            num = None
            m = re.search(r"№\s*([\d\-/]+)", row.get_text(" ", strip=True))
            if m:
                num = m.group(1)
            if not num and href:
                num = href.rstrip("/").split("/")[-1]
            price_txt = None
            for cell in row.select("td, .price, .nmck"):
                t = text(cell)
                if t and re.search(r"\d", t):
                    price_txt = t
                    break
            customer = text(row.select_one(".customer, .org, [class*='customer']"))
            deadline = text(row.select_one(".date, .deadline, time"))
            items.append(
                {
                    "title": title,
                    "nmck": parse_price(price_txt),
                    "customer_name": customer,
                    "submission_deadline_raw": deadline,
                    "registry_number": num or title[:80],
                    "external_url": href,
                }
            )
        if not items:
            for a in doc.select("a[href*='/procedure']"):
                t = text(a)
                if not t or len(t) < 10:
                    continue
                href = abs_url(self._base, str(a.get("href", "")))
                items.append(
                    {
                        "title": t,
                        "registry_number": href.split("/")[-1] if href else t[:40],
                        "external_url": href,
                    }
                )
        return items[:80]
