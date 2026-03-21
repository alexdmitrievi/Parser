"""fabrikant.ru — коммерческая площадка."""

from __future__ import annotations

import re
from typing import Any

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text


class FabrikantScraper(BaseScraper):
    source_platform = "fabrikant"
    law_type = "commercial"
    _base = "https://www.fabrikant.ru"

    def listing_url(self) -> str:
        return f"{self._base}/trades/"

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        for row in doc.select("tr, .trade-row, .lot-item, article, [data-trade-id]"):
            title_el = row.select_one("a[href*='/trades/'], .title a, h2 a, h3 a")
            if not title_el:
                continue
            title = text(title_el)
            if not title or len(title) < 5:
                continue
            link = abs_url(self._base, str(title_el.get("href", "")))
            num = None
            hn = row.find(string=re.compile(r"№\s*[\d\-/]+"))
            if hn:
                m = re.search(r"№\s*([\d\-/A-Za-z]+)", str(hn))
                if m:
                    num = m.group(1)
            if not num and link:
                m2 = re.search(r"/(\d+)/?$", link.split("?")[0])
                num = m2.group(1) if m2 else link
            price_txt = None
            for cell in row.select("td, .price, .sum"):
                t = text(cell)
                if t and any(x in t for x in ("₽", "руб", "RUB")):
                    price_txt = t
                    break
            customer = None
            for lab in ("Заказчик", "Организатор"):
                el = row.find(string=re.compile(lab, re.I))
                if el and el.parent:
                    customer = text(el.parent.find_next_sibling()) or text(el.parent)
                    break
            deadline = None
            for cell in row.select("td, .date, time"):
                t = text(cell)
                if t and re.search(r"\d{1,2}[./]\d{1,2}", t):
                    deadline = t
                    break
            items.append(
                {
                    "title": title,
                    "nmck": parse_price(price_txt),
                    "customer_name": customer,
                    "submission_deadline_raw": deadline,
                    "registry_number": num or title[:80],
                    "external_url": link,
                }
            )
        if not items:
            for a in doc.select("a[href*='/trades/']"):
                t = text(a)
                if not t or len(t) < 10:
                    continue
                href = abs_url(self._base, str(a.get("href", "")))
                items.append(
                    {
                        "title": t,
                        "registry_number": href.rstrip("/").split("/")[-1] if href else t[:40],
                        "external_url": href,
                    }
                )
        return items[:80]
