"""etp-ets.ru — НЭП (44-ФЗ и 223-ФЗ)."""

from __future__ import annotations

import re
from typing import Any

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text


class EtpEtsScraper(BaseScraper):
    """Два поиска: /44/search и /223/search — объединяются в run()."""

    source_platform = "etp_ets"
    law_type = "44-fz"
    _base = "https://etp-ets.ru"

    def listing_url(self) -> str:
        return f"{self._base}/44/search"

    def _parse_block(self, html: str, law: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        for row in doc.select("tr, .search-result, .lot-row, .card, article"):
            a = row.select_one("a[href*='/procedure'], a[href*='/purchase']")
            if not a:
                continue
            title = text(a)
            if not title or len(title) < 8:
                continue
            href = abs_url(self._base, str(a.get("href", "")))
            num = re.search(r"№\s*([\d\-/]+)", row.get_text(" ", strip=True))
            price_txt = text(row.select_one(".price, .nmck, [class*='price']"))
            items.append(
                {
                    "title": title,
                    "nmck": parse_price(price_txt),
                    "registry_number": (num.group(1) if num else href.split("/")[-1]),
                    "external_url": href,
                    "law_type": law,
                }
            )
        if not items:
            for a in doc.select("a[href*='/procedure'], a[href*='/purchase']"):
                t = text(a)
                if not t or len(t) < 10:
                    continue
                href = abs_url(self._base, str(a.get("href", "")))
                items.append(
                    {
                        "title": t,
                        "registry_number": href.rstrip("/").split("/")[-1],
                        "external_url": href,
                        "law_type": law,
                    }
                )
        return items[:60]

    def run(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        urls = (
            (f"{self._base}/44/search", "44-fz"),
            (f"{self._base}/223/search", "223-fz"),
        )
        for url, law in urls:
            html = self.fetch(url)
            if not html:
                continue
            for item in self._parse_block(html, law):
                item.setdefault("source_platform", self.source_platform)
                out.append(item)
        return out
