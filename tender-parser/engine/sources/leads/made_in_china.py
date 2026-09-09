"""Адаптер каталога поставщиков made-in-china.com.

Каталог сменил поисковый эндпоинт: старый ``/productdirectory.do`` отдаёт 404.
Актуальный — ``/products-search/hot-china-products/<slug>.html``, где ``slug`` —
ключевое слово в нижнем регистре с подчёркиваниями вместо пробелов. Страница
отдаёт ~16 карточек ``.products-item``: название компании (текст ссылки на
витрину поставщика ``*.en.made-in-china.com``) и регион (``Zhejiang, China``).

Собственный сайт компании каталог, как и раньше, не показывает — только витрину
на поддомене made-in-china, которая сайтом компании не считается. Поэтому
карточки пишутся с ``enrich_status=no_site`` (без домена) и дедуплицируются по
названию и провинции; ``enrich`` их пропускает, пока сайт не найден иным путём.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.parsers.utils import clean_text
from engine.sources.leads.base import LeadsSourceAdapter
from engine.types import (
    FetchMethod,
    RateLimitConfig,
    RetryConfig,
    SourceCategory,
    SourceConfig,
)
from leads.models import LeadCompany, utcnow
from leads.normalizer import parse_location, split_name_by_script

BASE_URL = "https://www.made-in-china.com"
SOURCE_ID = "made_in_china"

DEFAULT_SELECTORS = {
    "list_item": ".products-item",
    "company_name": "a[href$='.en.made-in-china.com']",
}


class MadeInChinaAdapter(LeadsSourceAdapter):
    """Каталог поставщиков made-in-china.com."""

    def discover(self) -> list[str]:
        """URL выдачи: по одному на английское ключевое слово профиля.

        Пагинации у «hot-china-products» нет — это кураторская выдача ~16
        карточек на запрос, поэтому лимит страниц не применяется.
        """
        keywords = self._keywords()
        if not keywords:
            self._log.warning("У профиля нет английских ключевых слов — обходить нечего")
            return []

        urls: list[str] = []
        for keyword in keywords:
            slug = keyword.strip().lower().replace(" ", "_")
            if not slug:
                continue
            urls.append(f"{BASE_URL}/products-search/hot-china-products/{slug}.html")
        return urls

    def _keywords(self) -> list[str]:
        """Только английские ключевые слова: slug в URL латинский."""
        if self.profile:
            return list(getattr(self.profile, "keywords_en", None) or [])
        return list(self.config.search_queries or [])

    def _selector(self, key: str) -> str:
        return self.config.get_selector(key, DEFAULT_SELECTORS.get(key, ""))

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Разобрать карточки ``.products-item`` в компании."""
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
            haystack = clean_text(block.get_text(" ", strip=True))
            province, city = parse_location(haystack)

            matched = self.profile.match(haystack) if self.profile else []
            industry = self.profile.guess_industry(haystack) if self.profile else ""

            companies.append(
                LeadCompany(
                    company_name_en=name_en,
                    company_name_zh=name_zh,
                    province=province,
                    city=city,
                    country="China",
                    matched_keywords=matched,
                    profile=self.profile.name if self.profile else "",
                    industry_guess=industry,
                    source_url=response.url,
                    source_name=SOURCE_ID,
                    first_seen=now,
                    last_seen=now,
                    enrich_status="no_site",  # сайт компании каталог не отдаёт
                )
            )

        return companies


MADE_IN_CHINA_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="made-in-china",
    category=SourceCategory.LEADS,
    base_url=BASE_URL,
    fetch_method=FetchMethod.HTTP,
    max_pages=1,
    selectors=dict(DEFAULT_SELECTORS),
    endpoints={"search": "/products-search/hot-china-products/{slug}.html"},
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
    "DEFAULT_SELECTORS",
    "MADE_IN_CHINA_CONFIG",
    "SOURCE_ID",
    "MadeInChinaAdapter",
    "get_made_in_china_adapter",
    "register_made_in_china",
]
