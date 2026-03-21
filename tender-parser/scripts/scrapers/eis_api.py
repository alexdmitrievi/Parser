"""Поиск по ЕИС (zakupki.gov.ru) через HTML-результаты расширенного поиска."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from scrapers.utils.html import abs_url, parse_price, soup, text

logger = logging.getLogger(__name__)

EIS_BASE = "https://zakupki.gov.ru"


class EisApiScraper(BaseScraper):
    """Расширенный поиск ЕИС: run() — 44+223, run_223() — только 223-ФЗ."""

    source_platform = "eis"
    law_type = "44-fz"
    timeout = 60

    QUERIES_223 = (
        "мебель 223-ФЗ",
        "поставка мебели",
        "офисная мебель",
        "подряд 223-ФЗ",
        "строительные работы",
        "капитальный ремонт",
        "текущий ремонт",
    )

    def _search_url(self, q: str, *, fz223: bool) -> str:
        qs = quote_plus(q)
        if fz223:
            return (
                f"{EIS_BASE}/epz/order/extendedsearch/results.html?"
                f"morphology=on&search-filter=%D0%94%D0%B0%D1%82%D0%B5+%D1%80%D0%B0%D0%B7%D0%BC%D0%B5%D1%89%D0%B5%D0%BD%D0%B8%D1%8F"
                f"&fz223=on&searchString={qs}"
            )
        return (
            f"{EIS_BASE}/epz/order/extendedsearch/results.html?"
            f"morphology=on&search-filter=%D0%94%D0%B0%D1%82%D0%B5+%D1%80%D0%B0%D0%B7%D0%BC%D0%B5%D1%89%D0%B5%D0%BD%D0%B8%D1%8F"
            f"&fz44=on&fz223=on&searchString={qs}"
        )

    def _parse_results_page(self, html: str, law: str) -> list[dict[str, Any]]:
        doc = soup(html)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for block in doc.select(
            ".search-registry-entry-block, .registry-entry, [data-registry], .row, tr"
        ):
            title_el = block.select_one(
                "a[href*='epz/order/notice'], a[href*='view'], .registry-entry__header a"
            )
            if not title_el:
                continue
            title = text(title_el)
            if not title or len(title) < 5:
                continue
            href = abs_url(EIS_BASE, str(title_el.get("href", "")))
            reg = None
            for pat in (r"№\s*([\d]+)", r"регистрационный\s+номер[:\s]+([\d]+)", r"\b(\d{19})\b"):
                m = re.search(pat, block.get_text(" ", strip=True), re.I)
                if m:
                    reg = m.group(1)
                    break
            if not reg and href:
                m2 = re.search(r"regNumber=([\w-]+)", href)
                reg = m2.group(1) if m2 else None
            key = reg or href
            if key in seen:
                continue
            seen.add(key)
            price_txt = text(block.select_one(".price-block, .currency, [class*='price']"))
            customer = text(
                block.select_one(
                    ".organization, .customer, .registry-entry__body, [class*='customer']"
                )
            )
            deadline = text(block.select_one(".data-block, .deadline, time, [class*='date']"))
            items.append(
                {
                    "title": title,
                    "nmck": parse_price(price_txt),
                    "customer_name": customer,
                    "submission_deadline_raw": deadline,
                    "registry_number": reg or key[:40],
                    "external_url": href or f"{EIS_BASE}/epz/order/extendedsearch/results.html",
                    "law_type": law,
                }
            )

        if not items:
            for a in doc.select("a[href*='epz/order/notice'], a[href*='view/common-info']"):
                t = text(a)
                if not t or len(t) < 15:
                    continue
                href = abs_url(EIS_BASE, str(a.get("href", "")))
                if href in seen:
                    continue
                seen.add(href)
                items.append(
                    {
                        "title": t,
                        "registry_number": href[-24:] if len(href) > 24 else href,
                        "external_url": href,
                        "law_type": law,
                    }
                )
        return items[:120]

    def parse_tenders(self, html: str) -> list[dict[str, Any]]:
        return self._parse_results_page(html, self.law_type)

    def listing_url(self) -> str:
        return self._search_url("строительные работы", fz223=False)

    def run(self) -> list[dict[str, Any]]:
        url = self._search_url("мебель офисная", fz223=False)
        html = self.fetch(url)
        if not html:
            return []
        raw = self._parse_results_page(html, "mixed")
        out: list[dict[str, Any]] = []
        for item in raw:
            item.setdefault("source_platform", self.source_platform)
            out.append(item)
        return out

    def run_223(self) -> list[dict[str, Any]]:
        """Только 223-ФЗ: fz223=on, без fz44; несколько поисковых запросов."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in self.QUERIES_223:
            url = self._search_url(q, fz223=True)
            html = self.fetch(url)
            if not html:
                logger.info("eis run_223: empty response for %s", q)
                continue
            for item in self._parse_results_page(html, "223-fz"):
                key = item.get("registry_number") or item.get("external_url") or item.get("title")
                if not key or key in seen:
                    continue
                seen.add(str(key))
                item.setdefault("source_platform", self.source_platform)
                item["law_type"] = "223-fz"
                out.append(item)
        return out
