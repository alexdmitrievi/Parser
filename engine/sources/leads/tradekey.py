"""Адаптер каталога поставщиков tradekey.com.

Глобальная B2B-площадка с поставщиками из КНР, Турции, Казахстана и других
стран. Используется как дополнительный источник к made_in_china для пилотных
профилей: импорт агротехники и экспорт зерна/мяса.

Как и у made_in_china, селекторы и формат URL поиска НЕ проверены на живой
вёрстке: они вынесены в ``SourceConfig.selectors`` / ``endpoints`` и правятся
конфигом без изменения кода.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.parsers.utils import clean_text
from engine.sources.leads.base import LeadsSourceAdapter
from engine.types import FetchMethod, RateLimitConfig, RetryConfig, SourceCategory, SourceConfig
from leads.models import LeadCompany, utcnow
from leads.normalizer import (
    is_company_domain,
    normalize_domain,
    normalize_website,
    parse_location,
    split_name_by_script,
)

BASE_URL = "https://www.tradekey.com"
SOURCE_ID = "tradekey"

DEFAULT_SELECTORS = {
    "list_item": ".search-result .item, .solo-list .item, .list-item, .company-item, .result-item",
    "company_name": ".company-name a, .name a, .title a, h2 a, h3 a",
    "company_link": ".company-name a, .name a, .title a, h2 a, h3 a",
    "location": ".location, .country, .company-location, .region",
    "website": ".website a, .company-website a, a[rel=nofollow]",
    "description": ".description, .desc, .company-desc, .summary",
}

# Шаблон URL поиска; {query} — URL-кодированное ключевое слово.
DEFAULT_ENDPOINTS = {"search": "/products/{query}/"}


class TradeKeyAdapter(LeadsSourceAdapter):
    """Каталог поставщиков tradekey.com."""

    def discover(self) -> list[str]:
        keywords = self._keywords()
        if not keywords:
            self._log.warning("У профиля нет ключевых слов — обходить нечего")
            return []

        max_pages = min(
            self.limits.max_pages_per_query,
            self.config.max_pages or self.limits.max_pages_per_query,
        )
        template = (self.config.endpoints or {}).get("search", "/products/{query}/")

        urls: list[str] = []
        for keyword in keywords:
            slug = quote_plus(keyword.lower().replace(" ", "-"))
            base = template.replace("{query}", slug)
            for page in range(1, max_pages + 1):
                urls.append(f"{BASE_URL}{base}?page={page}")
        return urls

    def _keywords(self) -> list[str]:
        if self.profile:
            return self.profile.all_keywords
        return list(self.config.search_queries or [])

    def _selector(self, key: str) -> str:
        return self.config.get_selector(key, DEFAULT_SELECTORS.get(key, ""))

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        soup = BeautifulSoup(response.text, "html.parser")
        blocks = soup.select(self._selector("list_item"))

        companies: list[LeadCompany] = []
        now = utcnow()

        for block in blocks:
            name_el = block.select_one(self._selector("company_name"))
            raw_name = clean_text(name_el.get_text()) if name_el else ""
            if not raw_name:
                continue

            name_en, name_zh = split_name_by_script(raw_name)

            link_el = block.select_one(self._selector("company_link")) or name_el
            href = link_el.get("href", "") if link_el else ""
            profile_url = urljoin(BASE_URL, str(href)) if href else response.url

            location_el = block.select_one(self._selector("location"))
            location_text = clean_text(location_el.get_text()) if location_el else ""
            province, city = parse_location(location_text or raw_name)

            description_el = block.select_one(self._selector("description"))
            description = clean_text(description_el.get_text()) if description_el else ""

            website, domain = self._extract_website(block, profile_url)

            haystack = " ".join(filter(None, (raw_name, description, location_text)))
            matched = self.profile.match(haystack) if self.profile else []
            industry = self.profile.guess_industry(haystack) if self.profile else ""

            companies.append(
                LeadCompany(
                    company_name_en=name_en,
                    company_name_zh=name_zh,
                    province=province,
                    city=city,
                    website=website,
                    domain=domain,
                    matched_keywords=matched,
                    profile=self.profile.name if self.profile else "",
                    industry_guess=industry,
                    source_url=profile_url,
                    source_name=SOURCE_ID,
                    first_seen=now,
                    last_seen=now,
                    enrich_status="pending" if domain else "no_site",
                )
            )

        return companies

    def _extract_website(self, block, profile_url: str) -> tuple[str, str]:
        website_el = block.select_one(self._selector("website"))
        if website_el:
            candidate = normalize_domain(str(website_el.get("href", "")))
            if candidate and is_company_domain(candidate):
                return normalize_website(candidate), candidate

        candidate = normalize_domain(profile_url)
        if candidate and is_company_domain(candidate):
            return normalize_website(candidate), candidate

        return "", ""


TRADEKEY_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="tradekey",
    category=SourceCategory.LEADS,
    base_url=BASE_URL,
    fetch_method=FetchMethod.HTTP,
    max_pages=20,
    selectors=dict(DEFAULT_SELECTORS),
    endpoints=dict(DEFAULT_ENDPOINTS),
    rate_limit=RateLimitConfig(min_delay=3.0, max_delay=6.0, max_concurrent=1),
    retry=RetryConfig(max_attempts=3, backoff_base=2.0, backoff_max=60.0),
    use_proxy=False,
    enabled=True,
)


def register_tradekey() -> None:
    from engine.config.registry import get_registry

    get_registry().register(TRADEKEY_CONFIG, TradeKeyAdapter)


def get_tradekey_adapter(profile=None, limits=None, **kwargs) -> TradeKeyAdapter:
    return TradeKeyAdapter(TRADEKEY_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "TradeKeyAdapter",
    "TRADEKEY_CONFIG",
    "register_tradekey",
    "get_tradekey_adapter",
    "SOURCE_ID",
    "DEFAULT_SELECTORS",
]
