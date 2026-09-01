"""Дедупликация компаний.

Ключ — нормализованный домен сайта. Если сайта нет, ключ собирается из
нормализованного названия и провинции.

Интерфейс повторяет :class:`engine.pipeline.deduplicator.Deduplicator`
(``check() -> CrawlAction``), но ключ и правила слияния — свои: тендерный
дедуп работает по ``registry_number``, которого у компаний нет.
"""

from __future__ import annotations

from typing import Any, Iterable

from engine.observability.logger import get_logger
from engine.types import CrawlAction
from leads.models import LeadCompany
from leads.normalizer import company_name_key

logger = get_logger("leads.dedup")

# Источники по убыванию доверия: данные из первого перекрывают остальные.
SOURCE_PRIORITY = ("customs_api", "seed_file", "made_in_china", "tradekey", "company_site")


def source_rank(source_name: str) -> int:
    """Позиция источника в приоритете; неизвестные — в конец."""
    try:
        return SOURCE_PRIORITY.index(source_name)
    except ValueError:
        return len(SOURCE_PRIORITY)


def company_key(company: LeadCompany) -> str:
    """Ключ дедупликации: домен, иначе название + провинция.

    Пустая строка означает, что запись неидентифицируема и её нельзя
    надёжно сопоставить — такие записи отбрасываются.
    """
    if company.domain:
        return f"domain:{company.domain}"

    name = company_name_key(company.company_name_en or company.company_name_zh)
    if not name:
        return ""

    province = (company.province or "").strip().lower()
    return f"name:{name}|{province}"


class LeadsDeduplicator:
    """Решает, что делать с найденной компанией: вставить, обновить, пропустить."""

    def check(
        self,
        incoming: LeadCompany,
        existing_map: dict[str, LeadCompany],
    ) -> CrawlAction:
        """Определить действие для найденной компании.

        Args:
            incoming: Компания из текущего прогона.
            existing_map: ``{ключ: уже сохранённая компания}``.

        Returns:
            ``INSERT`` — новая; ``UPDATE`` — известна, карточка обогащена
            и ``incoming`` содержит объединённые данные; ``SKIP`` — запись
            неидентифицируема.
        """
        key = company_key(incoming)
        if not key:
            logger.debug("Пропуск: у записи нет ни домена, ни названия")
            return CrawlAction.SKIP

        existing = existing_map.get(key)
        if existing is None:
            return CrawlAction.INSERT

        self.merge(incoming, existing)
        return CrawlAction.UPDATE

    def merge(self, incoming: LeadCompany, existing: LeadCompany) -> LeadCompany:
        """Слить сохранённую карточку в найденную.

        Пустые поля ``incoming`` заполняются из ``existing``. Непустые
        перекрываются только тогда, когда источник ``existing`` авторитетнее.
        Почты, телефоны и ключевые слова объединяются всегда.
        Изменяет и возвращает ``incoming``.
        """
        existing_wins = source_rank(existing.source_name) < source_rank(incoming.source_name)

        scalar_fields = (
            "company_name_en", "company_name_zh", "province", "city",
            "website", "domain", "wechat", "whatsapp", "industry_guess",
            "profile", "source_url", "source_name",
        )
        for field in scalar_fields:
            new_value = getattr(incoming, field, "")
            old_value = getattr(existing, field, "")
            if not new_value and old_value:
                setattr(incoming, field, old_value)
            elif existing_wins and old_value and field not in ("source_url", "source_name"):
                setattr(incoming, field, old_value)

        # Списки объединяются с сохранением порядка.
        incoming.matched_keywords = list(
            dict.fromkeys([*incoming.matched_keywords, *existing.matched_keywords])
        )
        incoming.phones = list(dict.fromkeys([*incoming.phones, *existing.phones]))

        # Почты: известные адреса не теряются, source_url первой находки важнее.
        known = {item.email: item for item in existing.emails}
        for item in incoming.emails:
            previous = known.get(item.email)
            if previous is None:
                known[item.email] = item
            else:
                previous.last_seen = item.last_seen
                if not previous.source_url:
                    previous.source_url = item.source_url
        incoming.emails = list(known.values())

        # first_seen — самое раннее из двух, last_seen — самое позднее.
        incoming.first_seen = min(incoming.first_seen, existing.first_seen)
        incoming.last_seen = max(incoming.last_seen, existing.last_seen)

        # Статус обогащения не откатываем к pending, если сайт уже обходили.
        if incoming.enrich_status == "pending" and existing.enrich_status != "pending":
            incoming.enrich_status = existing.enrich_status
            incoming.enrich_note = existing.enrich_note

        return incoming


def dedupe_batch(companies: Iterable[LeadCompany]) -> list[LeadCompany]:
    """Схлопнуть дубли внутри одной пачки, слив данные повторов."""
    dedup = LeadsDeduplicator()
    merged: dict[str, LeadCompany] = {}

    for company in companies:
        key = company_key(company)
        if not key:
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = company
        else:
            merged[key] = dedup.merge(company, existing)

    return list(merged.values())


def index_by_key(companies: Iterable[LeadCompany]) -> dict[str, LeadCompany]:
    """Построить ``{ключ: компания}`` для сравнения с сохранёнными."""
    index: dict[str, Any] = {}
    for company in companies:
        key = company_key(company)
        if key:
            index[key] = company
    return index


__all__ = [
    "LeadsDeduplicator",
    "company_key",
    "dedupe_batch",
    "index_by_key",
    "source_rank",
    "SOURCE_PRIORITY",
]
