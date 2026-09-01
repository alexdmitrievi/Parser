"""Пайплайн домена leads: сбор каталогов → обогащение сайтов → сохранение.

Это два шага одного прогона, а не независимые команды: каталоги дают домены,
``company_site`` обходит их и добавляет почты.

Отдельный пайплайн, а не :class:`~engine.pipeline.orchestrator.PipelineOrchestrator`,
потому что тот жёстко завязан на тендеры: тендерный нормализатор, теггер ниш,
дедуп по ``registry_number`` и таблица ``tenders``. Переиспользуются его
составные части — circuit breaker, health tracker, метрики, логгер, rate
limiter и retry.

Отказ одного источника не роняет прогон: источник помечается недоступным,
пишется в лог, остальные продолжают работать.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from engine.observability.health import get_health_tracker
from engine.observability.logger import CrawlLogger, new_correlation_id
from engine.observability.metrics import get_metrics
from engine.resilience.circuit_breaker import CircuitBreaker
from engine.sources.leads.base import LeadsSourceAdapter, SourceUnavailable
from engine.sources.leads.company_site import get_company_site_adapter
from engine.sources.leads.customs_api import get_customs_api_adapter
from engine.sources.leads.made_in_china import get_made_in_china_adapter
from engine.sources.leads.tradekey import get_tradekey_adapter
from engine.types import CrawlAction
from leads.dedup import LeadsDeduplicator, company_key, dedupe_batch
from leads.models import LeadCompany, utcnow
from leads.normalizer import is_company_domain, normalize_domain, normalize_website, split_name_by_script
from leads.profiles import Profile, ProfileConfig
from leads.seed import SeedRecord
from leads.storage.base import LeadsRepository

# Фабрики адаптеров-каталогов: дают карточки компаний.
CATALOG_FACTORIES: dict[str, Callable[..., LeadsSourceAdapter]] = {
    "made_in_china": get_made_in_china_adapter,
    "tradekey": get_tradekey_adapter,
    "customs_api": get_customs_api_adapter,
}

SEED_SOURCE_NAME = "seed_file"


@dataclass
class SourceOutcome:
    """Что случилось с одним источником."""

    source_id: str
    status: str = "ok"          # ok | blocked | unavailable | error
    found: int = 0
    note: str = ""
    skipped_by_robots: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class RunResult:
    """Итог одного прогона collect или enrich."""

    command: str
    profile: str = ""
    found: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    enriched: int = 0
    emails_added: int = 0
    duration_ms: int = 0
    sources: list[SourceOutcome] = field(default_factory=list)

    @property
    def status(self) -> str:
        """``success``, если хотя бы один источник отработал без блокировки."""
        if not self.sources:
            return "success"
        return "success" if any(s.ok for s in self.sources) else "failed"

    def summary(self) -> str:
        lines = [
            f"{self.command}: найдено {self.found}, "
            f"новых {self.inserted}, обновлено {self.updated}, пропущено {self.skipped}"
        ]
        if self.command == "enrich":
            lines.append(f"  обогащено компаний: {self.enriched}, новых почт: {self.emails_added}")
        for outcome in self.sources:
            mark = "OK" if outcome.ok else outcome.status.upper()
            detail = f" — {outcome.note}" if outcome.note else ""
            robots = (
                f", пропущено по robots.txt: {outcome.skipped_by_robots}"
                if outcome.skipped_by_robots
                else ""
            )
            lines.append(f"  [{mark}] {outcome.source_id}: {outcome.found}{robots}{detail}")
        return "\n".join(lines)


class LeadsPipeline:
    """Сбор и обогащение лидов."""

    def __init__(
        self,
        repository: LeadsRepository,
        profiles: ProfileConfig,
        deduplicator: LeadsDeduplicator | None = None,
    ):
        self._repo = repository
        self._profiles = profiles
        self._dedup = deduplicator or LeadsDeduplicator()
        self._metrics = get_metrics()
        self._health = get_health_tracker()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._log = CrawlLogger("leads")

    def _breaker(self, source_id: str) -> CircuitBreaker:
        if source_id not in self._circuit_breakers:
            self._circuit_breakers[source_id] = CircuitBreaker(source_id)
        return self._circuit_breakers[source_id]

    # ── шаг 1: сбор каталогов ──

    def collect(
        self,
        profile_name: str,
        sources: Iterable[str] | None = None,
        seed_domains: Iterable[str] | None = None,
        seed_records: Iterable[SeedRecord] | None = None,
    ) -> RunResult:
        """Обойти каталоги и сохранить найденные компании.

        Args:
            profile_name: Имя профиля из ``leads_profiles.yaml``.
            sources: Какие адаптеры запускать. ``None`` — все каталоги.
            seed_domains: Домены из файла-сида; добавляются как компании
                источника ``seed_file`` без обхода каталогов.
        """
        new_correlation_id()
        started = time.monotonic()
        profile = self._profiles.get(profile_name)
        result = RunResult(command="collect", profile=profile_name)

        companies: list[LeadCompany] = []

        seeded: list[LeadCompany] = []
        if seed_records is not None:
            seeded = self._companies_from_seed(seed_records, profile)
        elif seed_domains is not None:
            seeded = self._companies_from_domains(seed_domains, profile)
        if seeded:
            companies.extend(seeded)
            result.sources.append(
                SourceOutcome(source_id=SEED_SOURCE_NAME, found=len(seeded))
            )

        for source_id in self._catalog_ids(sources):
            outcome, found = self._run_catalog(source_id, profile)
            result.sources.append(outcome)
            companies.extend(found)

        result.found = len(companies)
        self._persist(dedupe_batch(companies), result)

        result.duration_ms = int((time.monotonic() - started) * 1000)
        self._log_run(result)
        return result

    def _catalog_ids(self, sources: Iterable[str] | None) -> list[str]:
        """Какие каталоги запускать с учётом LEADS_SOURCES и явного списка."""
        if sources is not None:
            requested = [s for s in sources if s]
        else:
            from shared.config import leads_enabled_sources

            requested = leads_enabled_sources()

        if not requested:
            return list(CATALOG_FACTORIES)

        selected = [s for s in requested if s in CATALOG_FACTORIES]
        unknown = [s for s in requested if s not in CATALOG_FACTORIES and s != "company_site"]
        for name in unknown:
            self._log.warning(f"Неизвестный источник '{name}' — пропускаю")
        return selected

    def _run_catalog(self, source_id: str, profile: Profile) -> tuple[SourceOutcome, list[LeadCompany]]:
        """Прогнать один каталог, не давая его отказу уронить весь запуск."""
        outcome = SourceOutcome(source_id=source_id)

        breaker = self._breaker(source_id)
        if not breaker.allow_request():
            outcome.status = "unavailable"
            outcome.note = "circuit breaker открыт"
            self._log.warning(f"{source_id}: circuit breaker открыт — пропускаю")
            return outcome, []

        if not self._health.is_available(source_id):
            outcome.status = "unavailable"
            outcome.note = "источник в cooldown после ошибок"
            self._log.warning(f"{source_id}: cooldown — пропускаю")
            return outcome, []

        factory = CATALOG_FACTORIES[source_id]
        adapter = factory(profile=profile, limits=self._profiles.limits)

        self._metrics.record_run_start(source_id)
        try:
            with adapter:
                found = adapter.collect()
        except SourceUnavailable as e:
            # Например, customs_api без ключа: это не ошибка прогона.
            outcome.status = "unavailable"
            outcome.note = str(e)
            self._log.info(f"{source_id}: {e} — пропускаю")
            return outcome, []
        except Exception as e:
            outcome.status = "error"
            outcome.note = str(e)[:200]
            breaker.record_failure()
            self._health.record_failure(source_id, str(e))
            self._log.error(f"{source_id}: прогон не удался: {e}")
            return outcome, []

        outcome.found = len(found)
        outcome.skipped_by_robots = len(adapter.skipped_by_robots)

        if adapter.blocked:
            outcome.status = "blocked"
            outcome.note = adapter.blocked_reason
            breaker.record_failure()
            self._health.record_failure(source_id, adapter.blocked_reason)
            self._log.warning(f"{source_id}: заблокирован ({adapter.blocked_reason})")
        else:
            breaker.record_success()
            self._health.record_success(source_id)

        self._metrics.record_parse(source_id, len(found))
        return outcome, found

    def _companies_from_domains(
        self, domains: Iterable[str], profile: Profile
    ) -> list[LeadCompany]:
        """Собрать карточки из файла-сида с доменами."""
        now = utcnow()
        companies: list[LeadCompany] = []
        for raw in domains:
            domain = normalize_domain(raw)
            if not domain:
                self._log.warning(f"Сид: не разобрал домен '{raw}' — пропускаю")
                continue
            if not is_company_domain(domain):
                self._log.warning(f"Сид: '{domain}' — агрегатор или почтовик, пропускаю")
                continue
            companies.append(
                LeadCompany(
                    website=normalize_website(domain),
                    domain=domain,
                    profile=profile.name,
                    source_name=SEED_SOURCE_NAME,
                    source_url="",
                    first_seen=now,
                    last_seen=now,
                    enrich_status="pending",
                )
            )
        return companies

    def _companies_from_seed(
        self, records: Iterable[SeedRecord], profile: Profile
    ) -> list[LeadCompany]:
        """Собрать карточки из файла-сида с названием, сайтом и страной."""
        now = utcnow()
        companies: list[LeadCompany] = []
        for rec in records:
            domain = normalize_domain(rec.website)
            if not domain:
                self._log.warning(f"Сид: не разобрал сайт '{rec.website}' — пропускаю")
                continue
            if not is_company_domain(domain):
                self._log.warning(f"Сид: '{domain}' — агрегатор или почтовик, пропускаю")
                continue
            name_en, name_zh = split_name_by_script(rec.name) if rec.name else ("", "")
            companies.append(
                LeadCompany(
                    company_name_en=name_en,
                    company_name_zh=name_zh,
                    website=normalize_website(domain),
                    domain=domain,
                    country=rec.country,
                    matched_keywords=[rec.hs_code] if rec.hs_code else [],
                    profile=profile.name,
                    source_name=SEED_SOURCE_NAME,
                    source_url="",
                    first_seen=now,
                    last_seen=now,
                    enrich_status="pending",
                )
            )
        return companies

    # ── шаг 2: обогащение сайтов ──

    def enrich(self, profile_name: str = "", limit: int = 0, retry_failed: bool = False) -> RunResult:
        """Обойти сайты собранных компаний и добрать почты.

        Args:
            profile_name: Ограничить профилем. Пусто — все.
            limit: Максимум компаний за прогон. 0 — без ограничения.
            retry_failed: Повторить домены, ранее давшие blocked/skipped_robots.
        """
        new_correlation_id()
        started = time.monotonic()
        result = RunResult(command="enrich", profile=profile_name)

        targets = self._enrich_targets(profile_name, limit, retry_failed)
        result.found = len(targets)
        if not targets:
            self._log.info("Нет компаний, требующих обогащения")
            result.duration_ms = int((time.monotonic() - started) * 1000)
            self._log_run(result)
            return result

        self._log.info(f"Обогащаю {len(targets)} компаний")
        enriched, robots_skipped, blocked = self._enrich_all(targets)

        result.enriched = sum(1 for c in enriched if c.enrich_status == "done")
        result.emails_added = sum(len(c.emails) for c in enriched)
        result.sources.append(
            SourceOutcome(
                source_id="company_site",
                status="blocked" if blocked and not result.enriched else "ok",
                found=result.enriched,
                skipped_by_robots=robots_skipped,
                note=f"заблокировано доменов: {blocked}" if blocked else "",
            )
        )

        self._persist(enriched, result)
        result.duration_ms = int((time.monotonic() - started) * 1000)
        self._log_run(result)
        return result

    def _enrich_targets(self, profile_name: str, limit: int, retry_failed: bool) -> list[LeadCompany]:
        """Компании с доменом, которые ещё не обходили (или обходили неудачно)."""
        targets = self._repo.iter_companies(
            profile=profile_name,
            enrich_status="pending",
            with_domain_only=True,
            limit=limit,
        )
        if retry_failed:
            for status in ("blocked", "skipped_robots"):
                remaining = (limit - len(targets)) if limit > 0 else 0
                if limit > 0 and remaining <= 0:
                    break
                targets.extend(
                    self._repo.iter_companies(
                        profile=profile_name,
                        enrich_status=status,
                        with_domain_only=True,
                        limit=remaining,
                    )
                )
        return targets

    def _enrich_all(self, targets: list[LeadCompany]) -> tuple[list[LeadCompany], int, int]:
        """Обойти сайты, соблюдая потолок конкурентности.

        Один домен всегда обрабатывается одним воркером целиком, поэтому
        параллельных запросов к одному хосту не бывает.
        """
        workers = max(1, min(self._profiles.limits.max_concurrency, len(targets)))
        local = threading.local()
        adapters: list[Any] = []
        adapters_lock = threading.Lock()

        def adapter_for_thread():
            existing = getattr(local, "adapter", None)
            if existing is None:
                existing = get_company_site_adapter(limits=self._profiles.limits)
                local.adapter = existing
                with adapters_lock:
                    adapters.append(existing)
            return existing

        def work(company: LeadCompany) -> LeadCompany:
            return adapter_for_thread().enrich(company)

        enriched: list[LeadCompany] = []
        try:
            if workers == 1:
                for company in targets:
                    enriched.append(self._safe_enrich(work, company))
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(self._safe_enrich, work, c): c for c in targets}
                    for future in as_completed(futures):
                        enriched.append(future.result())
        finally:
            for adapter in adapters:
                try:
                    adapter._polite.close()
                except Exception:  # noqa: BLE001 - закрытие не должно ронять прогон
                    pass

        robots_skipped = sum(1 for c in enriched if c.enrich_status == "skipped_robots")
        blocked = sum(1 for c in enriched if c.enrich_status == "blocked")
        return enriched, robots_skipped, blocked

    def _safe_enrich(
        self, work: Callable[[LeadCompany], LeadCompany], company: LeadCompany
    ) -> LeadCompany:
        """Обогатить одну компанию, не давая её падению уронить прогон."""
        try:
            return work(company)
        except Exception as e:
            self._log.error(f"{company.domain}: обогащение не удалось: {e}")
            company.enrich_status = "blocked"
            company.enrich_note = str(e)[:200]
            return company

    # ── сохранение ──

    def _persist(self, companies: list[LeadCompany], result: RunResult) -> None:
        """Слить с сохранёнными и записать в хранилище."""
        if not companies:
            return

        keys = [k for k in (company_key(c) for c in companies) if k]
        existing = self._repo.fetch_by_keys(keys)

        to_save: list[LeadCompany] = []
        for company in companies:
            action = self._dedup.check(company, existing)
            if action == CrawlAction.SKIP:
                result.skipped += 1
                continue
            if action == CrawlAction.INSERT:
                result.inserted += 1
            else:
                result.updated += 1
            to_save.append(company)

        if to_save:
            self._repo.upsert_companies(to_save)

    def _log_run(self, result: RunResult) -> None:
        """Записать прогон в leads_runs для мониторинга."""
        note = "; ".join(
            f"{o.source_id}:{o.status}" for o in result.sources if not o.ok
        )
        try:
            self._repo.log_run(
                command=result.command,
                profile=result.profile,
                found=result.found,
                inserted=result.inserted,
                updated=result.updated,
                status=result.status,
                note=note,
                duration_ms=result.duration_ms,
            )
        except Exception as e:
            self._log.warning(f"Не удалось записать лог прогона: {e}")


__all__ = ["LeadsPipeline", "RunResult", "SourceOutcome", "CATALOG_FACTORIES", "SEED_SOURCE_NAME"]
