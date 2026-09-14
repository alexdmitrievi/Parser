"""Адаптер каталога yell.ru (РФ): рубрики по городам.

Yell — гео-каталог организаций РФ (аналог 2ГИС без антибота): компании
сгруппированы по рубрикам ``/{city}/top/{rubric-slug}/``. robots.txt
разрешает рубричные страницы и страницы компаний, но запрещает любые URL
с query-параметрами (``Disallow: /*?``) — поэтому пагинация ``?page=N``
не обходится: берём первую страницу каждой рубрики (~30 компаний).

Разбор двухшаговый: листинг рубрики (имя, адрес, ссылка) → детальная
страница компании (телефон). Сайт и почта компании на yell обычно скрыты
за JS/Angular — их доберёт последующий enrich по домену-фильтру, поэтому
карточки из yell идут с ``enrich_status="no_site"``, кроме случаев, где
сайт виден в листинге.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.parsers.utils import clean_text
from engine.sources.leads.base import LeadsSourceAdapter
from engine.types import FetchMethod, RateLimitConfig, RetryConfig, SourceCategory, SourceConfig
from leads.models import LeadCompany, utcnow

BASE_URL = "https://www.yell.ru"
SOURCE_ID = "yell"

# Рубрики yell, релевантные B2B-нишам. Слаги фиксированы сайтом; список
# расширяется правкой YELL_RUBRICS без изменения кода.
YELL_RUBRICS: dict[str, str] = {
    "proizvodstvo-i-optovaya-torgovlya": "Производство и оптовая торговля",
    "stroitelstvo": "Строительство",
    "it-i-telekommunikacii": "IT и телекоммуникации",
    "marketing-i-reklama": "Маркетинг и реклама",
    "transport-i-logistika": "Транспорт и логистика",
    "uslugi": "Услуги",
}

# Города, по которым работает yell (фиксированный список сайта).
YELL_CITIES: list[str] = [
    "moscow", "spb", "yekaterinburg", "novosibirsk", "omsk", "kazan",
    "krasnodar", "nnovgorod", "perm", "rostov-na-donu", "samara", "saratov",
    "tolyatti", "tula", "ufa", "volgograd", "yaroslavl", "cheliabinsk", "lipetsk",
]

_COMPANY_HREF_RE = re.compile(r"^/([a-z-]+)/com/([a-z0-9-]+_\d+)/?(reviews/?)?$")
_PHONE_RE = re.compile(r"(\+7[\s()-]*\d{3}[\s()-]*\d{2}[\s()-]*\d{2}|\+7\d{10})")


def build_rubric_url(city: str, rubric_slug: str) -> str:
    """URL рубрики yell для города.

    Args:
        city: Слаг города (``omsk``, ``spb`` …).
        rubric_slug: Слаг рубрики (``stroitelstvo`` …).

    Returns:
        URL вида ``https://www.yell.ru/omsk/top/stroitelstvo/``.
    """
    return f"{BASE_URL}/{city.strip().lower()}/top/{rubric_slug.strip('/')}/"


def parse_listing_html(html: str, *, page_url: str, profile: str = "") -> list[LeadCompany]:
    """Разобрать листинг рубрики yell в карточки компаний.

    Args:
        html: HTML страницы рубрики.
        page_url: URL страницы (для ``source_url`` карточек).
        profile: Имя профиля/кампании.

    Returns:
        Список :class:`~leads.models.LeadCompany` (только имя + адрес + ссылка;
        контакты добираются детальной страницей и enrich).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies: list[LeadCompany] = []
    seen_hrefs: set[str] = set()
    now = utcnow()

    for item in soup.select("div.companies__item"):
        link = item.select_one("a[href]")
        if not link or not link.get("href"):
            continue
        raw_href = str(link["href"]).split("?")[0]
        match = _COMPANY_HREF_RE.match(raw_href)
        if not match:
            continue
        # /reviews/ суффикс — та же компания; нормализуем к базовой ссылке.
        href = f"/{match.group(1)}/com/{match.group(2)}"
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        title_el = item.select_one(".companies__item-title a") or link
        name = clean_text(title_el.get_text())
        if not name:
            continue

        address_el = item.select_one(".companies__item-address")
        address = clean_text(address_el.get_text()) if address_el else ""

        companies.append(
            LeadCompany(
                company_name_en=name,
                country="Russia",
                activity=address[:300],
                profile=profile,
                source_url=f"{BASE_URL}{href}/",
                source_name=SOURCE_ID,
                first_seen=now,
                last_seen=now,
                enrich_status="no_site",
            )
        )
    return companies


def parse_company_page(html: str) -> dict[str, str]:
    """Разобрать детальную страницу компании yell.

    Args:
        html: HTML страницы компании.

    Returns:
        Словарь с ключами ``phone`` и ``address`` (пустые строки, если
        данных нет).
    """
    soup = BeautifulSoup(html, "html.parser")

    phone = ""
    phone_el = soup.find("span", itemprop="telephone")
    if phone_el:
        phone = clean_text(phone_el.get_text())
    if not phone:
        match = _PHONE_RE.search(soup.get_text())
        phone = match.group(1) if match else ""

    address = ""
    addr_el = soup.find("span", itemprop="streetAddress")
    if addr_el:
        address = clean_text(addr_el.get_text())

    return {"phone": phone, "address": address}


class YellAdapter(LeadsSourceAdapter):
    """Каталог организаций yell.ru (РФ, рубрики по городам)."""

    def discover(self) -> list[str]:
        keywords = self._keywords()
        rubrics = self._match_rubrics(keywords)
        cities = self._cities()
        urls: list[str] = []
        for city in cities:
            for slug in rubrics:
                urls.append(build_rubric_url(city, slug))
        return urls

    def _keywords(self) -> list[str]:
        if self.profile:
            return [
                *self.profile.keywords_en,
                *self.profile.keywords_zh,  # слот «не-латиница» = keywords_ru
            ]
        return list(self.config.search_queries or [])

    def _match_rubrics(self, keywords: list[str]) -> list[str]:
        """Рубрики, чьё название пересекается с ключевыми словами кампании."""
        matched: list[str] = []
        lowered = [k.lower() for k in keywords if k]
        for slug, title in YELL_RUBRICS.items():
            title_lower = title.lower()
            if not lowered or any(k in title_lower or title_lower in k for k in lowered):
                matched.append(slug)
        return matched or list(YELL_RUBRICS)

    def _cities(self) -> list[str]:
        """Города обхода: из стран профиля — РФ, ограничено списком yell."""
        if self.profile and "russia" not in {c.lower() for c in self.profile.countries}:
            return []
        return YELL_CITIES

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        profile_name = self.profile.name if self.profile else ""
        companies = parse_listing_html(
            response.text, page_url=response.url, profile=profile_name
        )

        # Детальные страницы: добираем телефон (сайт/почта — через enrich).
        for company in companies:
            try:
                detail = self.fetch_page(company.source_url)
            except Exception:  # noqa: BLE001 - одна страница не роняет рубрику
                continue
            if not detail.ok:
                continue
            info = parse_company_page(detail.text)
            if info["phone"]:
                company.phones = [info["phone"]]
            if info["address"] and not company.activity:
                company.activity = info["address"][:300]

        return companies


YELL_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="yell",
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


def register_yell() -> None:
    from engine.config.registry import get_registry

    get_registry().register(YELL_CONFIG, YellAdapter)


def get_yell_adapter(profile=None, limits=None, **kwargs) -> YellAdapter:
    return YellAdapter(YELL_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "YellAdapter",
    "YELL_CONFIG",
    "YELL_CITIES",
    "YELL_RUBRICS",
    "BASE_URL",
    "SOURCE_ID",
    "build_rubric_url",
    "get_yell_adapter",
    "parse_company_page",
    "parse_listing_html",
    "register_yell",
]
