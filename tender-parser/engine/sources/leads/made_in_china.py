"""Адаптер каталога поставщиков made-in-china.com.

Обходит выдачу по ключевым запросам профиля с пагинацией и разбирает карточки
компаний: название (латиница + иероглифы), провинция, город, ссылка на профиль.

Два предупреждения, о которых надо знать до первого запуска:

1. **Селекторы не проверены на живой вёрстке.** Они вынесены в
   ``SourceConfig.selectors`` и заданы цепочками с запасными вариантами.
   Если каталог отдаёт другую разметку — правится конфиг, не код.
   См. раздел «Если каталог поменял вёрстку» в docs/LEADS.md.

2. **Каталог может запрещать обход поисковой выдачи в robots.txt.** Тогда
   адаптер честно ничего не соберёт: запрет логируется, прогон продолжается
   с остальными источниками. Обходить запрет нельзя. Рабочая альтернатива —
   ``leads collect --from-file domains.txt`` или платный ``customs_api``.

Собственный домен компании каталог, как правило, не показывает: ссылка ведёт
на витрину вида ``supplier.en.made-in-china.com``. Такие адреса не считаются
сайтом компании (см. ``NON_COMPANY_HOSTS``), поэтому карточка без настоящего
домена дедуплицируется по названию и провинции, а ``enrich`` её пропускает.
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

BASE_URL = "https://www.made-in-china.com"
SOURCE_ID = "made_in_china"

# Цепочки селекторов: перебираются по очереди до первого совпадения.
DEFAULT_SELECTORS = {
    "list_item": (
        ".prod-list .item, .list-node, .prod-item, .company-item, "
        ".search-list .item, .cmp-list .item, li.J-faw-item"
    ),
    "company_name": (
        ".company-name a, .compnay-name a, .co-name a, .cmp-name a, "
        ".company-info .name a, h2 a, .title a"
    ),
    "company_link": (
        ".company-name a, .compnay-name a, .co-name a, .cmp-name a, "
        ".company-info .name a, h2 a, .title a"
    ),
    "location": (
        ".company-location, .compnay-address, .prod-company-loc, "
        ".location, .province, .cmp-location, .company-info .loc"
    ),
    "website": ".company-website a, .website a, a.site-link",
    "description": ".prod-name, .product-name, .cmp-desc, .company-desc, .desc",
}


class MadeInChinaAdapter(LeadsSourceAdapter):
    """Каталог поставщиков made-in-china.com."""

    def discover(self) -> list[str]:
        """URL выдачи: ключевые слова профиля × страницы пагинации."""
        keywords = self._keywords()
        if not keywords:
            self._log.warning("У профиля нет ключевых слов — обходить нечего")
            return []

        max_pages = min(
            self.limits.max_pages_per_query,
            self.config.max_pages or self.limits.max_pages_per_query,
        )
        search_path = (self.config.endpoints or {}).get("search", "/productdirectory.do")

        urls: list[str] = []
        for keyword in keywords:
            encoded = quote_plus(keyword)
            for page in range(1, max_pages + 1):
                urls.append(
                    f"{BASE_URL}{search_path}"
                    f"?word={encoded}&file=&mode=and&comProvince=nolimit"
                    f"&order=0&isOpenCorrePage=1&page={page}"
                )
        return urls

    def _keywords(self) -> list[str]:
        """Ключевые слова профиля; при его отсутствии — search_queries конфига."""
        if self.profile:
            return self.profile.all_keywords
        return list(self.config.search_queries or [])

    def _selector(self, key: str) -> str:
        return self.config.get_selector(key, DEFAULT_SELECTORS.get(key, ""))

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Разобрать страницу выдачи в карточки компаний."""
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
        """Настоящий сайт компании, если карточка его показывает.

        Витрина внутри каталога сайтом компании не считается.
        """
        website_el = block.select_one(self._selector("website"))
        if website_el:
            candidate = normalize_domain(str(website_el.get("href", "")))
            if candidate and is_company_domain(candidate):
                return normalize_website(candidate), candidate

        candidate = normalize_domain(profile_url)
        if candidate and is_company_domain(candidate):
            return normalize_website(candidate), candidate

        return "", ""


# ── Конфиг и регистрация ──

MADE_IN_CHINA_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="made-in-china",
    category=SourceCategory.LEADS,
    base_url=BASE_URL,
    fetch_method=FetchMethod.HTTP,
    max_pages=20,
    selectors=dict(DEFAULT_SELECTORS),
    endpoints={"search": "/productdirectory.do"},
    # Вежливый режим: задержка не меньше конфига профиля, прокси запрещены.
    rate_limit=RateLimitConfig(min_delay=3.0, max_delay=6.0, max_concurrent=1),
    retry=RetryConfig(max_attempts=3, backoff_base=2.0, backoff_max=60.0),
    use_proxy=False,
    enabled=True,
)


def register_made_in_china() -> None:
    """Зарегистрировать адаптер в общем реестре источников."""
    from engine.config.registry import get_registry

    get_registry().register(MADE_IN_CHINA_CONFIG, MadeInChinaAdapter)


def get_made_in_china_adapter(profile=None, limits=None, **kwargs) -> MadeInChinaAdapter:
    """Готовый адаптер каталога для указанного профиля."""
    return MadeInChinaAdapter(MADE_IN_CHINA_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "MadeInChinaAdapter",
    "MADE_IN_CHINA_CONFIG",
    "register_made_in_china",
    "get_made_in_china_adapter",
    "SOURCE_ID",
    "DEFAULT_SELECTORS",
]
