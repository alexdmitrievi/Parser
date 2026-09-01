"""Базовый класс адаптеров домена leads.

Наследует инфраструктуру :class:`~engine.sources.base.BaseSourceAdapter`
(конфиг, rate limiter, логгер, жизненный цикл), но подменяет транспорт:

* вместо :class:`~engine.fetchers.http_fetcher.HttpFetcher` с ротацией
  User-Agent используется :class:`~engine.fetchers.polite_fetcher.PoliteFetcher`
  с честным UA и без прокси;
* каждый URL перед запросом проверяется через :class:`RobotsGate`;
* блокировка источника (403/429/капча) не роняет прогон: адаптер помечается
  недоступным, пишет в лог и возвращает то, что успел собрать.

Адаптеры leads возвращают :class:`~leads.models.LeadCompany`, а не
``ParsedRecord``: это другая сущность, и подмешивать её в тендерный
нормализатор нельзя.
"""

from __future__ import annotations

from typing import Iterable

from engine.fetchers.polite_fetcher import PoliteFetcher, PoliteResponse, SourceBlocked
from engine.fetchers.robots import RobotsGate
from engine.observability.logger import CrawlLogger
from engine.resilience.rate_limiter import RateLimiter
from engine.sources.base import BaseSourceAdapter
from engine.types import ParsedRecord, RetryConfig, SourceConfig
from leads.models import LeadCompany
from leads.profiles import Limits, Profile


class SourceUnavailable(Exception):
    """Источник не может работать в текущей конфигурации.

    Например, ``customs_api`` без ключа подписки. Это не ошибка прогона:
    источник пропускается, остальные продолжают работать.
    """


class LeadsSourceAdapter(BaseSourceAdapter):
    """Базовый адаптер leads: вежливый транспорт + robots + сбор компаний.

    Подкласс обязан реализовать:
        * :meth:`parse_companies` — разбор страницы в список компаний.

    Может переопределить:
        * :meth:`discover` — построение списка URL;
        * :meth:`availability` — проверку, что источник вообще может работать.
    """

    def __init__(
        self,
        config: SourceConfig,
        profile: Profile | None = None,
        limits: Limits | None = None,
        user_agent: str = "",
        fetcher: PoliteFetcher | None = None,
        robots: RobotsGate | None = None,
    ):
        super().__init__(config)
        self.profile = profile
        self.limits = limits or Limits()
        self._log = CrawlLogger(config.source_id)

        if not user_agent and fetcher is None:
            from shared.config import leads_user_agent

            user_agent = leads_user_agent()
        self._user_agent = user_agent or (fetcher.user_agent if fetcher else "")

        # Вежливая задержка берётся из профиля, но не может быть меньше
        # заданной в конфиге источника.
        delay = max(
            self.limits.request_delay_seconds,
            config.rate_limit.min_delay if config.rate_limit else 0.0,
        )
        self._rate_limiter = RateLimiter(
            min_delay=delay,
            max_delay=max(delay, config.rate_limit.max_delay if config.rate_limit else delay),
            max_concurrent=1,
        )

        if fetcher is None:
            from shared.config import firecrawl_api_key, leads_firecrawl_sources

            fk = firecrawl_api_key()
            if fk and config.source_id in leads_firecrawl_sources():
                from engine.fetchers.firecrawl_fetcher import FirecrawlFetcher

                fetcher = FirecrawlFetcher(
                    api_key=fk,
                    rate_limiter=self._rate_limiter,
                    retry_config=config.retry or RetryConfig(),
                    source_id=config.source_id,
                    user_agent=self._user_agent,
                )

        self._polite = fetcher or PoliteFetcher(
            user_agent=self._user_agent,
            rate_limiter=self._rate_limiter,
            retry_config=config.retry or RetryConfig(),
            source_id=config.source_id,
        )
        self._robots = robots or RobotsGate(self._polite, self._user_agent)

        self.blocked = False
        self.blocked_reason = ""
        self.skipped_by_robots: list[str] = []

    # ── доступность ──

    def availability(self) -> tuple[bool, str]:
        """Может ли источник работать. ``(False, причина)`` — будет пропущен."""
        return True, ""

    def ensure_available(self) -> None:
        """Бросить :class:`SourceUnavailable`, если источник работать не может."""
        ok, reason = self.availability()
        if not ok:
            raise SourceUnavailable(reason)

    # ── транспорт ──

    def _get_fetcher(self) -> PoliteFetcher:  # type: ignore[override]
        """Вежливый фетчер вместо ротирующего UA HttpFetcher из базы."""
        return self._polite

    def robots_allows(self, url: str) -> bool:
        """Разрешает ли robots.txt обход URL. Запрет логируется."""
        if self._robots.can_fetch(url):
            return True
        reason = self._robots.skip_reason(url) or "disallowed by robots.txt"
        self._log.info(f"ROBOTS SKIP {url}: {reason}")
        self.skipped_by_robots.append(url)
        return False

    def fetch_page(self, url: str) -> PoliteResponse:  # type: ignore[override]
        """Скачать страницу, соблюдая robots.txt и Crawl-delay.

        Raises:
            PermissionError: обход URL запрещён robots.txt.
            SourceBlocked: сайт нас заблокировал — обход прекращается.
        """
        if not self.robots_allows(url):
            raise PermissionError(f"robots.txt disallows {url}")

        # Crawl-delay сайта имеет приоритет, если он больше нашего.
        site_delay = self._robots.effective_delay(url, self._rate_limiter.min_delay)
        if site_delay > self._rate_limiter.min_delay:
            self._log.debug(f"Crawl-delay {site_delay}s from robots.txt for {url}")
            self._rate_limiter.min_delay = site_delay
            self._rate_limiter.max_delay = max(self._rate_limiter.max_delay, site_delay)

        return self._polite.fetch(url)

    # ── разбор ──

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Разобрать страницу в список компаний. Обязателен к реализации."""
        raise NotImplementedError(
            f"{self.__class__.__name__} должен реализовать parse_companies()"
        )

    def parse_listing(self, result) -> list[ParsedRecord]:  # type: ignore[override]
        """Не применимо: адаптеры leads отдают LeadCompany, а не ParsedRecord."""
        raise NotImplementedError(
            "Адаптеры leads используют parse_companies() → list[LeadCompany]. "
            "parse_listing() относится к тендерному пайплайну и здесь не вызывается."
        )

    # ── сбор ──

    def collect(self) -> list[LeadCompany]:
        """Обойти источник целиком и вернуть найденные компании.

        Блокировка или запрет robots.txt не роняет прогон: возвращается то,
        что удалось собрать до остановки.
        """
        self.ensure_available()

        companies: list[LeadCompany] = []
        urls = list(self.discover())
        self._log.info(f"Discovered {len(urls)} target URLs")

        for url in urls:
            try:
                response = self.fetch_page(url)
            except PermissionError:
                continue  # уже залогировано в robots_allows
            except SourceBlocked as e:
                self.blocked = True
                self.blocked_reason = e.reason
                self._log.warning(
                    f"BLOCKED {url}: {e.reason} — прекращаю обход этого источника"
                )
                break
            except Exception as e:
                self._log.fetch_fail(url, str(e))
                continue

            if not response.ok:
                self._log.fetch_fail(url, f"HTTP {response.status_code}")
                continue

            try:
                page_companies = self.parse_companies(response)
            except Exception as e:
                self._log.parse_fail(url, str(e))
                continue

            self._log.parse_ok(len(page_companies), url)
            companies.extend(page_companies)

            if not page_companies:
                # Пустая страница — дальше по пагинации идти незачем.
                self._log.debug(f"Пустая страница {url} — останавливаю пагинацию")
                break

        return companies

    # ── жизненный цикл ──

    def __exit__(self, *exc) -> None:  # type: ignore[override]
        self._polite.close()


def dedupe_companies(companies: Iterable[LeadCompany]) -> list[LeadCompany]:
    """Убрать повторы внутри одного прогона по домену, иначе по имени+провинции."""
    seen: set[str] = set()
    unique: list[LeadCompany] = []
    for company in companies:
        key = company.domain or f"{company.display_name.lower()}|{company.province.lower()}"
        if not key.strip("|") or key in seen:
            continue
        seen.add(key)
        unique.append(company)
    return unique


__all__ = ["LeadsSourceAdapter", "SourceUnavailable", "dedupe_companies"]
