"""Abstract repository interface for tender/auction/grant persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class TenderRepository(ABC):
    """Abstract interface for tender storage.

    Concrete implementations: Supabase, PostgreSQL, etc.
    """

    @abstractmethod
    def upsert_batch(
        self,
        records: list[dict[str, Any]],
        conflict_keys: tuple[str, ...] = ("source_platform", "registry_number"),
        batch_size: int = 200,
    ) -> int:
        """Upsert records with dedup. Returns count of upserted records."""
        ...

    @abstractmethod
    def fetch_existing_by_registry(
        self,
        registry_numbers: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch existing records by registry number. Returns {registry_number: record}."""
        ...

    @abstractmethod
    def fetch_record_by_id(self, record_id: str) -> Optional[dict[str, Any]]:
        """Fetch single record by primary key."""
        ...

    @abstractmethod
    def update_record(self, record_id: str, updates: dict[str, Any]) -> bool:
        """Update specific fields of a record."""
        ...

    @abstractmethod
    def store_snapshot(
        self,
        registry_number: str,
        source_platform: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Store a raw snapshot for versioning/audit."""
        ...
