"""Адаптер каталога поставщиков all.biz.

Глобальная B2B-площадка с продавцами из КНР, Турции, Казахстана и других
стран. Поиск по товару возвращает страницу категории со списком оферт;
каждая оферта ведёт на страницу, в которой лежит JSON-LD с контактами
продавца — имя, email, телефон, страна/город/адрес и описание.

Сбор двухшаговый: листинг категории → детальная страница оферты (JSON-LD).
Селекторы вынесены в ``SourceConfig.selectors`` и правятся конфигом.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.parsers.utils import clean_text
from engine.sources.leads.base import LeadsSourceAdapter
from engine.types import FetchMethod, RateLimitConfig, RetryConfig, SourceCategory, SourceConfig
from leads.models import LeadCompany, LeadEmail, utcnow
from leads.normalizer import is_company_domain, normalize_domain, normalize_website

BASE_URL = "https://all.biz"
SOURCE_ID = "allbiz"

DEFAULT_SELECTORS = {
    "list_item": ".b-product--grid-item",
    "company_name": ".company-name-text, .company-name",
    "offer_link": ".b-product--grid__name a, a[href*='-g']",
    "product": ".b-product--grid__name",
}

# Домены бесплатной почты — из них сайт компании не вывести.
_FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "mail.ru",
    "yandex.ru", "inbox.ru", "list.ru", "bk.ru", "icloud.com", "aol.com",
    "protonmail.com", "qq.com", "163.com", "126.com", "sina.com",
}

# Приоритетные страны лидогена (решение владельца): КНР, Турция, Казахстан.
# Страна продавца кодируется в суффиксе URL оферты (…-gNNNNNNCN) и в
# JSON-LD addressCountry. Фильтруем по обоим, чтобы не фетчить лишнее.
TARGET_COUNTRY_CODES = frozenset({"CN", "TR", "KZ"})
_COUNTRY_SUFFIX_RE = re.compile(r"-g\d+([A-Z]{2})$")


class AllBizAdapter(LeadsSourceAdapter):
    """Каталог поставщиков all.biz."""

    def discover(self) -> list[str]:
        keywords = self._keywords()
        if not keywords:
            self._log.warning("У профиля нет английских ключевых слов — обходить нечего")
            return []
        return [
            f"{BASE_URL}/search/goods?q={quote_plus(keyword)}"
            for keyword in keywords
        ]

    def _keywords(self) -> list[str]:
        if self.profile:
            return list(getattr(self.profile, "keywords_en", None) or self.profile.all_keywords)
        return list(self.config.search_queries or [])

    def _selector(self, key: str) -> str:
        return self.config.get_selector(key, DEFAULT_SELECTORS.get(key, ""))

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Листинг категории → карточки компаний (с детальным фетчем оферт)."""
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select(self._selector("list_item"))

        companies: list[LeadCompany] = []
        now = utcnow()

        for card in cards:
            offer_url = self._offer_url(card, response.url)
            if not offer_url:
                continue
            country_code = self._country_code(offer_url)
            if country_code and country_code not in TARGET_COUNTRY_CODES:
                continue  # страна вне приоритета — не фетчим детальную страницу

            try:
                detail = self._polite.fetch(offer_url)
            except Exception as exc:  # noqa: BLE001 - отдельная оферта не роняет прогон
                self._log.fetch_fail(offer_url, str(exc))
                continue
            if not detail.ok:
                continue

            info = self._parse_ld(detail.text)
            if not info.get("name"):
                continue
            if info.get("country") and not self._is_target_country(info["country"]):
                continue  # страна из JSON-LD вне приоритета

            domain = self._derive_domain(info.get("email", ""))
            email = info.get("email", "")
            company = LeadCompany(
                company_name_en=info["name"],
                website=normalize_website(domain) if domain else "",
                domain=domain,
                country=info.get("country", ""),
                city=info.get("city", ""),
                province=info.get("region", ""),
                activity=info.get("description", "")[:300],
                offers=[info.get("description", "")[:300]] if info.get("description") else [],
                profile=self.profile.name if self.profile else "",
                source_url=offer_url,
                source_name=SOURCE_ID,
                first_seen=now,
                last_seen=now,
                enrich_status="pending" if domain else "no_site",
            )
            if email:
                company.add_emails([LeadEmail(email=email.lower(), source_url=offer_url)])
            companies.append(company)

        return companies

    def _offer_url(self, card, page_url: str) -> str:
        link = card.select_one(self._selector("offer_link"))
        if not link or not link.get("href"):
            return ""
        return urljoin(page_url, str(link["href"]))

    @staticmethod
    def _country_code(url: str) -> str:
        """ISO-код страны продавца из суффикса URL оферты (…-gNNNNNNKZ)."""
        match = _COUNTRY_SUFFIX_RE.search(url)
        return match.group(1) if match else ""

    @staticmethod
    def _is_target_country(name: str) -> bool:
        """Принадлежит ли имя страны из JSON-LD приоритетной тройке."""
        normalized = name.lower().replace("ü", "u")
        return any(key in normalized for key in ("china", "kazakhstan", "turk"))

    @staticmethod
    def _parse_ld(html: str) -> dict[str, str]:
        """Вытащить контакты продавца из JSON-LD на странице оферты."""
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if not isinstance(item, dict) or "email" not in item:
                    continue
                address = item.get("address") or {}
                email = str(item.get("email", "")).replace("mailto:", "").strip()
                return {
                    "name": clean_text(str(item.get("name", ""))),
                    "email": email,
                    "country": clean_text(str(address.get("addressCountry", ""))),
                    "city": clean_text(str(address.get("addressLocality", ""))),
                    "region": clean_text(str(address.get("addressRegion", ""))),
                    "description": clean_text(str(item.get("description", ""))),
                }
        return {}

    @staticmethod
    def _derive_domain(email: str) -> str:
        """Домен компании из корпоративной почты; пустая строка для фримейла."""
        if "@" not in email:
            return ""
        domain = normalize_domain(email.rsplit("@", 1)[1])
        if not domain or domain in _FREEMAIL_DOMAINS:
            return ""
        if not is_company_domain(domain):
            return ""
        return domain


ALLBIZ_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="allbiz",
    category=SourceCategory.LEADS,
    base_url=BASE_URL,
    fetch_method=FetchMethod.HTTP,
    max_pages=20,
    selectors=dict(DEFAULT_SELECTORS),
    rate_limit=RateLimitConfig(min_delay=2.0, max_delay=4.0, max_concurrent=1),
    retry=RetryConfig(max_attempts=3, backoff_base=2.0, backoff_max=60.0),
    use_proxy=False,
    enabled=True,
)


def register_allbiz() -> None:
    from engine.config.registry import get_registry

    get_registry().register(ALLBIZ_CONFIG, AllBizAdapter)


def get_allbiz_adapter(profile=None, limits=None, **kwargs) -> AllBizAdapter:
    return AllBizAdapter(ALLBIZ_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "AllBizAdapter",
    "ALLBIZ_CONFIG",
    "register_allbiz",
    "get_allbiz_adapter",
    "SOURCE_ID",
    "DEFAULT_SELECTORS",
]
