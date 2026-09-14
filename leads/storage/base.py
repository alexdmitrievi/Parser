"""Интерфейс хранилища лидов.

Все таблицы/коллекции имеют префикс ``leads_``, чтобы не пересекаться с
существующими ``tenders``, ``funding_programs`` и прочими.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from leads.models import LeadCompany

# Имена таблиц вынесены в константы: используются и в миграции, и в запросах.
TABLE_COMPANIES = "leads_companies"
TABLE_EMAILS = "leads_emails"
TABLE_RUNS = "leads_runs"


class LeadsRepository(ABC):
    """Хранилище компаний и их почт."""

    @abstractmethod
    def migrate(self) -> None:
        """Создать схему, если её нет. Обязана быть идемпотентной."""

    @abstractmethod
    def upsert_companies(self, companies: list[LeadCompany]) -> tuple[int, int]:
        """Сохранить компании. Возвращает ``(вставлено, обновлено)``."""

    @abstractmethod
    def fetch_by_keys(self, keys: list[str]) -> dict[str, LeadCompany]:
        """Прочитать сохранённые компании по ключам дедупликации."""

    @abstractmethod
    def iter_companies(
        self,
        profile: str = "",
        enrich_status: str = "",
        with_domain_only: bool = False,
        limit: int = 0,
    ) -> list[LeadCompany]:
        """Выбрать компании с фильтрами. ``limit=0`` — без ограничения."""

    @abstractmethod
    def stats(self, profile: str = "") -> dict[str, Any]:
        """Сводка: компании, почты, разбивка по профилям и провинциям."""

    @abstractmethod
    def log_run(
        self,
        command: str,
        profile: str,
        found: int,
        inserted: int,
        updated: int,
        status: str,
        note: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Записать результат прогона для мониторинга."""

    def close(self) -> None:
        """Освободить ресурсы. По умолчанию ничего не делает."""


__all__ = ["LeadsRepository", "TABLE_COMPANIES", "TABLE_EMAILS", "TABLE_RUNS"]
