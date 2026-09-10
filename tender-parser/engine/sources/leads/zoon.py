"""Адаптер каталога zoon.ru (РФ): рубрики по городам.

Zoon — гео-каталог организаций РФ. Организации лежат по рубрикам
``/{city}/{rubric}/`` с пагинацией ``page-N`` (запрещена robots.txt
``Disallow: /*page=`` — берём только первую страницу). Страница организации
отдаёт имя, адрес (microdata itemprop), телефон и сайт: сайт прячется в
escaped-JSON блоке подписи фотографий («Фото взято с сайта <a href=…>»),
а телефон — в тексте описания.

Сбор двухшаговый: листинг рубрики → детальная страница организации.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.parsers.utils import clean_text
from engine.sources.leads.base import LeadsSourceAdapter
from engine.types import FetchMethod, RateLimitConfig, RetryConfig, SourceCategory, SourceConfig
from leads.models import LeadCompany, utcnow
from leads.normalizer import is_company_domain, normalize_domain, normalize_website

BASE_URL = "https://zoon.ru"
SOURCE_ID = "zoon"

# Рубрики zoon, релевантные B2B-нишам (верхний уровень каталога).
ZOON_RUBRICS: dict[str, str] = {
    "building": "Строительство",
    "business": "Бизнес-услуги",
    "internet": "Интернет-компании",
    "repair": "Ремонт и техника",
    "shops": "Магазины",
    "stores": "Склады и оптовая торговля",
    "public_services": "Госуслуги",
    "realty": "Недвижимость",
    "utility_service": "Коммунальные услуги",
}

# Города zoon (слаги сайта; крупные B2B-центры РФ).
ZOON_CITIES: list[str] = [
    "msk", "spb", "ekb", "novosibirsk", "omsk", "kazan", "krasnodar",
    "krasnoyarsk", "nizhniy-novgorod", "perm", "rostov-na-donu", "samara",
    "ufa", "chelyabinsk", "voronezh", "volgograd", "tyumen", "barnaul",
    "irkutsk", "kemerovo",
]

# Ссылка на организацию: /{city}/{rubric}/{org-slug}(/) — без type/price/page.
_ORG_HREF_RE = re.compile(r"^/([a-z0-9-]+)/([a-z0-9-]+)/([a-z0-9_-]+(?:-[a-f0-9]{4})?)/?$")
_PHONE_RE = re.compile(r"(\+7(?:[\s\xa0()\-]*\d){10})")
_SITE_JSON_RE = re.compile(r'href=\\?"https?://([a-z0-9.-]+\.[a-z]{2,})')
_SITE_TEXT_RE = re.compile(r"посетите сайт\s+([a-z0-9.-]+\.[a-z]{2,})")

# Части URL, которые точно не организации.
_NON_ORG_PARTS = ("type", "price", "page-", "reviews", "photo")


def build_rubric_url(city: str, rubric_slug: str) -> str:
    """URL рубрики zoon для города.

    Args:
        city: Слаг города (``omsk``, ``msk`` …).
        rubric_slug: Слаг рубрики (``building`` …).

    Returns:
        URL вида ``https://zoon.ru/omsk/building/``.
    """
    return f"{BASE_URL}/{city.strip().lower()}/{rubric_slug.strip('/')}/"


def extract_org_links(html: str, *, base: str) -> list[str]:
    """Вытащить ссылки на страницы организаций из листинга рубрики.

    Args:
        html: HTML страницы рубрики.
        base: URL страницы (для нормализации относительных ссылок).

    Returns:
        Уникальные абсолютные URL страниц организаций в порядке появления.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[str] = []

    for link in soup.find_all("a", href=True):
        href = str(link["href"]).split("?")[0].split("#")[0]
        path = href if href.startswith("/") else urljoin(base, href)
        path = path[len(BASE_URL) :] if path.startswith(BASE_URL) else path
        match = _ORG_HREF_RE.match(path)
        if not match:
            continue
        # type/price/page — служебные пути, не организации.
        if any(part in path for part in _NON_ORG_PARTS):
            continue
        url = f"{BASE_URL}{path}"
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def parse_org_page(html: str) -> dict[str, str]:
    """Разобрать страницу организации zoon.

    Args:
        html: HTML страницы организации.

    Returns:
        Словарь с ключами ``name``, ``phone``, ``address``, ``city``,
        ``site``, ``description`` (пустые строки, если данных нет).
    """
    soup = BeautifulSoup(html, "html.parser")

    name = ""
    name_el = soup.find("span", itemprop="name")
    if name_el:
        name = clean_text(name_el.get_text())

    address = ""
    addr_el = soup.find("span", itemprop="streetAddress")
    if addr_el:
        address = clean_text(addr_el.get_text())

    city = ""
    city_el = soup.find("meta", itemprop="addressLocality")
    if city_el and city_el.get("content"):
        city = clean_text(str(city_el["content"]))

    phone = ""
    match = _PHONE_RE.search(html)
    if match:
        phone = " ".join(match.group(1).split())

    # Сайт: сначала escaped-JSON подписи фото, затем упоминание в тексте.
    site = ""
    match = _SITE_JSON_RE.search(html)
    if match:
        site = f"https://{match.group(1)}"
    else:
        match = _SITE_TEXT_RE.search(html)
        if match:
            site = f"https://{match.group(1)}"

    return {
        "name": name,
        "phone": phone,
        "address": address,
        "city": city,
        "site": site,
        "description": "",
    }


class ZoonAdapter(LeadsSourceAdapter):
    """Каталог организаций zoon.ru (РФ, рубрики по городам)."""

    def discover(self) -> list[str]:
        keywords = self._keywords()
        rubrics = self._match_rubrics(keywords)
        cities = self._cities()
        return [build_rubric_url(city, slug) for city in cities for slug in rubrics]

    def _keywords(self) -> list[str]:
        if self.profile:
            return [
                *self.profile.keywords_en,
                *self.profile.keywords_zh,  # слот «не-латиница» = keywords_ru
            ]
        return list(self.config.search_queries or [])

    def _match_rubrics(self, keywords: list[str]) -> list[str]:
        """Рубрики zoon, чьё название пересекается с ключевыми словами."""
        matched: list[str] = []
        lowered = [k.lower() for k in keywords if k]
        for slug, title in ZOON_RUBRICS.items():
            title_lower = title.lower()
            if not lowered or any(k in title_lower or title_lower in k for k in lowered):
                matched.append(slug)
        return matched or list(ZOON_RUBRICS)

    def _cities(self) -> list[str]:
        if self.profile and "russia" not in {c.lower() for c in self.profile.countries}:
            return []
        return ZOON_CITIES

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Листинг рубрики → организации (с фетчем детальных страниц)."""
        org_urls = extract_org_links(response.text, base=response.url)
        companies: list[LeadCompany] = []
        now = utcnow()
        profile_name = self.profile.name if self.profile else ""

        for org_url in org_urls:
            try:
                detail = self.fetch_page(org_url)
            except Exception:  # noqa: BLE001 - одна организация не роняет рубрику
                continue
            if not detail.ok:
                continue

            info = parse_org_page(detail.text)
            if not info["name"]:
                continue

            domain = ""
            if info["site"]:
                candidate = normalize_domain(info["site"])
                if candidate and is_company_domain(candidate):
                    domain = candidate

            company = LeadCompany(
                company_name_en=info["name"],
                country="Russia",
                city=info["city"],
                activity=(info["address"] or info["description"])[:300],
                website=normalize_website(domain) if domain else "",
                domain=domain,
                phones=[info["phone"]] if info["phone"] else [],
                profile=profile_name,
                source_url=org_url,
                source_name=SOURCE_ID,
                first_seen=now,
                last_seen=now,
                enrich_status="pending" if domain else "no_site",
            )
            companies.append(company)

        return companies


ZOON_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="zoon",
    category=SourceCategory.LEADS,
    base_url=BASE_URL,
    fetch_method=FetchMethod.HTTP,
    max_pages=1,
    selectors={},
    rate_limit=RateLimitConfig(min_delay=3.0, max_delay=6.0, max_concurrent=1),
    retry=RetryConfig(max_attempts=2, backoff_base=2.0, backoff_max=30.0),
    use_proxy=False,
    enabled=True,
)


def register_zoon() -> None:
    from engine.config.registry import get_registry

    get_registry().register(ZOON_CONFIG, ZoonAdapter)


def get_zoon_adapter(profile=None, limits=None, **kwargs) -> ZoonAdapter:
    return ZoonAdapter(ZOON_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "ZoonAdapter",
    "ZOON_CONFIG",
    "ZOON_CITIES",
    "ZOON_RUBRICS",
    "BASE_URL",
    "SOURCE_ID",
    "build_rubric_url",
    "extract_org_links",
    "get_zoon_adapter",
    "parse_org_page",
    "register_zoon",
]
