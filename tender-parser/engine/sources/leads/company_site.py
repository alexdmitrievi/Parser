"""Адаптер обхода сайта компании: поиск контактных страниц и почт.

Второй шаг пайплайна. На вход — домены, собранные каталогами; на выход — почты,
телефоны и мессенджеры, добавленные в карточку компании.

Порядок обхода одного домена:

1. Проверяется ``robots.txt``. Запрещённые пути не запрашиваются вообще.
2. Скачивается главная страница; из её ссылок отбираются кандидаты в контактные
   (``contact``, ``about``, ``contact-us``, ``联系我们``, ``关于我们`` и подобные).
3. Кандидаты обходятся до ``max_pages_per_domain``, с той же вежливой задержкой.
4. Со всех страниц собираются почты; остаются только адреса на домене компании.

Блокировка (403/429/капча) прекращает обход **этого домена**, остальные
продолжают обрабатываться.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from engine.fetchers.polite_fetcher import PoliteResponse, SourceBlocked
from engine.parsers.utils import clean_text
from engine.sources.leads.base import LeadsSourceAdapter
from engine.types import FetchMethod, RateLimitConfig, RetryConfig, SourceCategory, SourceConfig
from leads.emails import emails_for_domain, extract_emails
from leads.models import LeadCompany, utcnow
from leads.normalizer import detect_city, detect_province, split_name_by_script

SOURCE_ID = "company_site"

# Маркеры контактных страниц: в URL или в тексте ссылки.
CONTACT_MARKERS = (
    "contact", "contact-us", "contactus", "contact_us",
    "about", "about-us", "aboutus", "about_us",
    "reach-us", "get-in-touch", "impressum", "inquiry", "enquiry",
    "联系我们", "联系方式", "关于我们", "公司简介", "联系",
)

# Пути, которые заведомо не содержат контактов, — не тратим на них запросы.
SKIP_MARKERS = (
    "/cart", "/login", "/register", "/signin", "/signup", "/search",
    "/privacy", "/terms", "/sitemap", "/feed", "/rss", "/wp-json",
    ".pdf", ".jpg", ".png", ".zip", ".doc", ".xls",
)

# Типичные пути контактных страниц — пробуются, даже если ссылки на них нет.
FALLBACK_PATHS = ("/contact", "/contact-us", "/about", "/about-us", "/contactus")

DEFAULT_MAX_PAGES_PER_DOMAIN = 5

_PHONE_RE = re.compile(r"(?:\+?86[\s\-]?)?(?:\d[\s\-()]?){7,15}\d")
_WECHAT_RE = re.compile(
    r"(?:wechat|weixin|微信)\s*(?:id|ID|号|:|：|-)?\s*([A-Za-z0-9_\-]{5,30})", re.IGNORECASE
)
_WHATSAPP_RE = re.compile(
    r"(?:whatsapp|whats\s*app)\s*(?::|：|-)?\s*(\+?[\d\s\-()]{7,20})", re.IGNORECASE
)


class CompanySiteAdapter(LeadsSourceAdapter):
    """Обход сайта компании ради контактов."""

    def __init__(self, *args, max_pages_per_domain: int = DEFAULT_MAX_PAGES_PER_DOMAIN, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages_per_domain = max_pages_per_domain

    # ── публичный вход ──

    def enrich(self, company: LeadCompany) -> LeadCompany:
        """Обогатить карточку контактами с её сайта.

        Обновляет ``enrich_status``:
            ``done`` — сайт обойдён; ``no_site`` — домена нет;
            ``skipped_robots`` — обход запрещён robots.txt;
            ``blocked`` — сайт нас заблокировал.
        """
        if not company.domain:
            company.enrich_status = "no_site"
            company.enrich_note = "домен компании неизвестен"
            return company

        root, status, note = self._resolve_root(company.domain)
        if root is None:
            company.enrich_status = status
            company.enrich_note = note
            self._log.info(f"SKIP {company.domain}: {note}")
            return company

        pages: list[PoliteResponse] = []
        try:
            home = self.fetch_page(root)
            if home.ok:
                pages.append(home)
                for url in self._contact_urls(home, company.domain, root):
                    if len(pages) >= self.max_pages_per_domain:
                        break
                    try:
                        page = self.fetch_page(url)
                    except PermissionError:
                        continue
                    if page.ok:
                        pages.append(page)
        except PermissionError:
            company.enrich_status = "skipped_robots"
            company.enrich_note = "disallowed by robots.txt"
            return company
        except SourceBlocked as e:
            company.enrich_status = "blocked"
            company.enrich_note = e.reason
            self._log.warning(f"BLOCKED {company.domain}: {e.reason}")
            return company
        except Exception as e:
            company.enrich_status = "blocked"
            company.enrich_note = str(e)[:200]
            self._log.fetch_fail(root, str(e))
            return company

        if not pages:
            company.enrich_status = "blocked"
            company.enrich_note = "не удалось скачать ни одной страницы"
            return company

        self._harvest(company, pages)
        company.enrich_status = "done"
        company.last_seen = utcnow()
        return company

    # ── внутреннее ──

    def _resolve_root(self, domain: str) -> tuple[str | None, str, str]:
        """Найти рабочий origin сайта: сначала https, при недоступности — http.

        Множество китайских сайтов до сих пор без TLS, поэтому одной только
        https-попытки мало. Это не обход защиты: у каждой схемы свой
        robots.txt, и он соблюдается отдельно.

        Явный ``Disallow`` останавливает сразу — вторую схему не пробуем.
        Нечитаемый robots.txt (сеть, TLS, 5xx) — повод проверить другую схему.

        Returns:
            ``(origin | None, статус, пояснение)``.
        """
        status, note = "blocked", "не удалось открыть сайт"

        for scheme in ("https", "http"):
            root = f"{scheme}://{domain}/"

            if self._robots.can_fetch(root):
                return root, "", ""

            if self._robots.host_unreachable(root):
                # robots.txt не прочитан — возможно, работает другая схема.
                status = "skipped_robots"
                note = self._robots.skip_reason(root)
                continue

            # robots.txt прочитан и явно запрещает — останавливаемся.
            self.skipped_by_robots.append(root)
            self._log.info(f"ROBOTS SKIP {root}: disallowed by robots.txt")
            return None, "skipped_robots", "disallowed by robots.txt"

        return None, status, note

    def _contact_urls(self, home: PoliteResponse, domain: str, root: str) -> list[str]:
        """Кандидаты в контактные страницы: из ссылок главной + типовые пути."""
        soup = BeautifulSoup(home.text, "html.parser")
        candidates: list[str] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            absolute = urljoin(home.url, href)
            parts = urlsplit(absolute)
            if parts.scheme not in ("http", "https"):
                continue

            host = (parts.hostname or "").lower().removeprefix("www.")
            if host != domain and not host.endswith("." + domain):
                continue  # внешние ссылки не обходим

            lowered = absolute.lower()
            if any(marker in lowered for marker in SKIP_MARKERS):
                continue

            label = clean_text(anchor.get_text()).lower()
            haystack = f"{lowered} {label}"
            if not any(marker in haystack for marker in CONTACT_MARKERS):
                continue

            normalized = absolute.split("#", 1)[0]
            if normalized in seen or normalized == home.url:
                continue
            seen.add(normalized)
            candidates.append(normalized)

        # Типовые пути на случай, если в навигации ссылок нет.
        for path in FALLBACK_PATHS:
            fallback = root.rstrip("/") + path
            if fallback not in seen:
                seen.add(fallback)
                candidates.append(fallback)

        return candidates

    def _harvest(self, company: LeadCompany, pages: list[PoliteResponse]) -> None:
        """Снять почты, телефоны и мессенджеры со скачанных страниц."""
        for page in pages:
            found = extract_emails(page.text, source_url=page.url)
            company.add_emails(emails_for_domain(found, company.domain))

            text = self._page_text(page.text)
            self._harvest_messengers(company, text)
            self._harvest_phones(company, text)

            if not company.province:
                company.province = detect_province(text)
            if not company.city:
                company.city = detect_city(text)
            if not company.company_name_en and not company.company_name_zh:
                self._harvest_name(company, page.text)

    @staticmethod
    def _harvest_name(company: LeadCompany, html: str) -> None:
        """Название из ``og:site_name`` или ``<title>``.

        Нужно для компаний из файла-сида: там известен только домен.
        """
        soup = BeautifulSoup(html, "html.parser")

        candidate = ""
        meta = soup.find("meta", attrs={"property": "og:site_name"})
        if meta and meta.get("content"):
            candidate = clean_text(str(meta["content"]))
        if not candidate and soup.title and soup.title.string:
            # У заголовков часто есть хвост после разделителя — берём первую часть.
            candidate = clean_text(re.split(r"[|\-–—:·]", soup.title.string, maxsplit=1)[0])

        if not candidate or len(candidate) > 120:
            return

        name_en, name_zh = split_name_by_script(candidate)
        company.company_name_en = name_en
        company.company_name_zh = name_zh

    @staticmethod
    def _page_text(html: str) -> str:
        """Видимый текст страницы без скриптов и стилей."""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)

    @staticmethod
    def _harvest_messengers(company: LeadCompany, text: str) -> None:
        if not company.wechat:
            match = _WECHAT_RE.search(text)
            if match:
                company.wechat = match.group(1).strip()
        if not company.whatsapp:
            match = _WHATSAPP_RE.search(text)
            if match:
                company.whatsapp = re.sub(r"[^\d+]", "", match.group(1))

    @staticmethod
    def _harvest_phones(company: LeadCompany, text: str) -> None:
        """Телефоны с китайской нумерацией; максимум пять на компанию."""
        known = set(company.phones)
        for match in _PHONE_RE.finditer(text):
            digits = re.sub(r"[^\d+]", "", match.group(0))
            if not 8 <= len(digits.lstrip("+")) <= 15:
                continue
            if digits in known:
                continue
            known.add(digits)
            company.phones.append(digits)
            if len(company.phones) >= 5:
                return

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Не применимо: адаптер обогащает существующие карточки."""
        raise NotImplementedError(
            "company_site обогащает уже собранные карточки — используйте enrich()."
        )

    def discover(self) -> list[str]:
        """Не применимо: список доменов приходит из хранилища."""
        return []


# ── Конфиг и регистрация ──

COMPANY_SITE_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="company-site",
    category=SourceCategory.LEADS,
    base_url="",
    fetch_method=FetchMethod.HTTP,
    max_pages=DEFAULT_MAX_PAGES_PER_DOMAIN,
    rate_limit=RateLimitConfig(min_delay=3.0, max_delay=5.0, max_concurrent=1),
    retry=RetryConfig(max_attempts=2, backoff_base=2.0, backoff_max=30.0),
    use_proxy=False,
    enabled=True,
)


def register_company_site() -> None:
    from engine.config.registry import get_registry

    get_registry().register(COMPANY_SITE_CONFIG, CompanySiteAdapter)


def get_company_site_adapter(profile=None, limits=None, **kwargs) -> CompanySiteAdapter:
    return CompanySiteAdapter(COMPANY_SITE_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "CompanySiteAdapter",
    "COMPANY_SITE_CONFIG",
    "register_company_site",
    "get_company_site_adapter",
    "SOURCE_ID",
    "CONTACT_MARKERS",
]
