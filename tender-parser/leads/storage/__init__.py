"""Хранилище лидов.

Две реализации одного интерфейса:

* :class:`~leads.storage.sqlite_repo.SqliteLeadsRepository` — локальный файл,
  используется по умолчанию. CLI и тесты работают без облака.
* :class:`~leads.storage.supabase_repo.SupabaseLeadsRepository` — таблицы
  ``leads_*`` в общем проекте Supabase; включается ``LEADS_STORAGE=supabase``.

Выбор делает :func:`get_leads_repository` по переменным окружения.
"""

from __future__ import annotations

from leads.storage.base import LeadsRepository

__all__ = ["LeadsRepository", "get_leads_repository"]


def get_leads_repository(storage: str | None = None) -> LeadsRepository:
    """Создать хранилище по конфигурации.

    Args:
        storage: ``sqlite`` или ``supabase``. По умолчанию — ``LEADS_STORAGE``.

    Raises:
        ValueError: неизвестный бэкенд.
    """
    from shared.config import leads_db_path, leads_storage

    backend = (storage or leads_storage()).lower()

    if backend == "sqlite":
        from leads.storage.sqlite_repo import SqliteLeadsRepository

        return SqliteLeadsRepository(leads_db_path())

    if backend == "supabase":
        from leads.storage.supabase_repo import SupabaseLeadsRepository

        return SupabaseLeadsRepository()

    raise ValueError(
        f"Неизвестный LEADS_STORAGE='{backend}'. Допустимо: sqlite, supabase."
    )
