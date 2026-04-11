"""Corporate portal template adapter.

Replaces 6 near-identical scrapers (Gazprom, Rosatom, Rosneft, Lukoil, Nornickel, MTS)
with a single config-driven adapter.

Each corporate portal uses the same HTML structure:
- Listing blocks: .purchase-row, .purchase-item, tr[data-id], .tender-item, etc.
- Title link: a[href*='/purchase'], a[href*='/procedure'], h3 a
- Price: .price, .sum, .nmck, .cost
- Customer: .customer, .organizer, .company
- Deadline: .deadline, .end-date, .date-end, time
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from engine.types import (
    SourceConfig, FetchResult, ParsedRecord, SourceCategory, FetchMethod,
    RateLimitConfig,
)
from engine.sources.base import BaseSourceAdapter
from engine.parsers.utils import parse_price, parse_date, clean_text
from engine.config.registry import get_registry


# ── Block selectors (common across corporate portals) ──

BLOCK_SELECTORS = (
    ".purchase-row, .purchase-item, .search-result, "
    "tr[data-id], .lot-card, .tender-item, article, "
    "[class*='procedure'], [class*='purchase'], [class*='tender']"
)

LINK_SELECTORS = (
    "a[href*='/purchase'], a[href*='/procedure'], a[href*='/lot'], "
    "a.purchase-link, h3 a, h2 a, a.title"
)

FALLBACK_LINK_SELECTORS = "a[href*='/purchase'], a[href*='/procedure']"


class CorporateSourceAdapter(BaseSourceAdapter):
    """Config-driven adapter for corporate procurement portals.

    Works for any portal with standard HTML listing + search endpoint.
    """

    def parse_listing(self, result: FetchResult) -> list[ParsedRecord]:
        soup = BeautifulSoup(result.content, "html.parser")
        records: list[ParsedRecord] = []
        base = self.config.base_url

        blocks = soup.select(BLOCK_SELECTORS)

        for block in blocks:
            link = block.select_one(LINK_SELECTORS)
            if not link:
                continue

            title = clean_text(link.get_text())
            if not title or len(title) < 5:
                continue

            href = link.get("href", "")
            url = base + href if href.startswith("/") else href

            # Try to extract registry number from text or URL
            num_match = re.search(r"(\d{6,})", link.get_text() + href)
            registry_number = num_match.group(1) if num_match else None

            # Price
            price_el = block.select_one(".price, .sum, .nmck, .cost")
            nmck = parse_price(price_el.get_text()) if price_el else None

            # Customer
            customer_el = block.select_one(".customer, .organizer, .org-name, .company")
            customer = clean_text(customer_el.get_text()) if customer_el else None

            # Deadline
            deadline_el = block.select_one(".deadline, .end-date, .date-end, time")
            deadline_text = deadline_el.get_text(strip=True) if deadline_el else ""
            deadline = parse_date(deadline_text)

            records.append(ParsedRecord(
                source_id=self.config.source_id,
                registry_number=registry_number,
                title=title,
                original_url=url,
                nmck=nmck,
                customer_name=customer,
                submission_deadline=deadline,
                raw_data={"html_block": str(block)[:500]},
            ))

        # Fallback: if no blocks matched, try raw link extraction
        if not records:
            for a in soup.select(FALLBACK_LINK_SELECTORS):
                t = clean_text(a.get_text())
                if not t or len(t) < 10:
                    continue
                href = a.get("href", "")
                full_url = base + href if href.startswith("/") else href
                records.append(ParsedRecord(
                    source_id=self.config.source_id,
                    registry_number=href.rstrip("/").split("/")[-1] if href else None,
                    title=t,
                    original_url=full_url,
                    raw_data={},
                ))

        return records[:80]


# ══════════════════════════════════════════════
# Corporate portal configurations
# ══════════════════════════════════════════════

_CORPORATE_SOURCES = [
    {
        "source_id": "gazprom",
        "platform_name": "gazprom",
        "base_url": "https://etpgaz.gazprom.ru",
        "endpoints": {
            "search": "/rfx/search",
            "query_param": "query",
            "page_param": "page",
        },
        "search_queries": [
            "поставка оборудования", "ремонт", "строительство",
            "газоснабжение", "техническое обслуживание", "транспорт",
        ],
    },
    {
        "source_id": "rosatom",
        "platform_name": "rosatom",
        "base_url": "https://zakupki.rosatom.ru",
        "endpoints": {"search": "/search", "query_param": "q", "page_param": "page"},
        "search_queries": [
            "поставка оборудования", "ремонт", "строительство",
            "атомная энергия", "техническое обслуживание", "транспорт",
        ],
    },
    {
        "source_id": "rosneft",
        "platform_name": "rosneft",
        "base_url": "https://zakupki.rosneft.ru",
        "endpoints": {"search": "/search", "query_param": "q", "page_param": "page"},
        "search_queries": [
            "поставка оборудования", "ремонт", "строительство",
            "нефтепродукты", "техническое обслуживание", "транспорт",
        ],
    },
    {
        "source_id": "lukoil",
        "platform_name": "lukoil",
        "base_url": "https://tender.lukoil.ru",
        "endpoints": {"search": "/search", "query_param": "q", "page_param": "page"},
        "search_queries": [
            "поставка оборудования", "ремонт", "строительство",
            "нефтепродукты", "техническое обслуживание", "транспорт",
        ],
    },
    {
        "source_id": "nornickel",
        "platform_name": "nornickel",
        "base_url": "https://tenders.nornickel.ru",
        "endpoints": {"search": "/search", "query_param": "q", "page_param": "page"},
        "search_queries": [
            "поставка оборудования", "ремонт", "строительство",
            "горнодобыча", "техническое обслуживание", "транспорт",
        ],
    },
    {
        "source_id": "mts",
        "platform_name": "mts",
        "base_url": "https://tenders.mts.ru",
        "endpoints": {"search": "/search", "query_param": "q", "page_param": "page"},
        "search_queries": [
            "поставка оборудования", "ремонт", "строительство",
            "IT услуги", "телекоммуникации", "техническое обслуживание",
        ],
    },
]


def _make_corporate_config(src: dict) -> SourceConfig:
    return SourceConfig(
        source_id=src["source_id"],
        platform_name=src["platform_name"],
        category=SourceCategory.TENDERS,
        base_url=src["base_url"],
        fetch_method=FetchMethod.HTTP,
        search_queries=src["search_queries"],
        max_pages=2,
        endpoints=src["endpoints"],
        rate_limit=RateLimitConfig(min_delay=3.0, max_delay=7.0),
        law_type_default="223-fz",
    )


def register_corporate_sources() -> None:
    """Register all 6 corporate sources in the global registry."""
    registry = get_registry()
    for src in _CORPORATE_SOURCES:
        cfg = _make_corporate_config(src)
        registry.register(cfg, CorporateSourceAdapter)


def get_corporate_adapter(source_id: str) -> CorporateSourceAdapter:
    """Create a corporate adapter for a specific source."""
    for src in _CORPORATE_SOURCES:
        if src["source_id"] == source_id:
            return CorporateSourceAdapter(_make_corporate_config(src))
    raise ValueError(f"Unknown corporate source: {source_id}")


def get_all_corporate_adapters() -> list[CorporateSourceAdapter]:
    """Create adapters for all 6 corporate sources."""
    return [
        CorporateSourceAdapter(_make_corporate_config(src))
        for src in _CORPORATE_SOURCES
    ]
