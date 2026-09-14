"""Supabase implementation of TenderRepository.

Wraps existing shared.db functions to maintain backward compatibility,
while providing the clean Repository interface for the new engine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from engine.persistence.repository import TenderRepository

logger = logging.getLogger("engine.persistence.supabase")


class SupabaseTenderRepository(TenderRepository):
    """Supabase-backed tender repository. Delegates to shared.db for compatibility."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from shared.config import get_config
            from supabase import create_client
            cfg = get_config()
            self._client = create_client(cfg["supabase_url"], cfg["supabase_key"])
        return self._client

    def upsert_batch(
        self,
        records: list[dict[str, Any]],
        conflict_keys: tuple[str, ...] = ("source_platform", "registry_number"),
        batch_size: int = 200,
    ) -> int:
        if not records:
            return 0

        db = self._get_client()

        # Deduplicate within batch
        seen: set[tuple] = set()
        unique_rows: list[dict] = []
        for rec in records:
            key = tuple(str(rec.get(k, "")) for k in conflict_keys)
            if key in seen:
                continue
            seen.add(key)

            # Serialize datetime fields
            row = dict(rec)
            for dt_field in ("publish_date", "submission_deadline", "auction_date"):
                if isinstance(row.get(dt_field), datetime):
                    row[dt_field] = row[dt_field].isoformat()
            unique_rows.append(row)

        total = 0
        on_conflict = ",".join(conflict_keys)

        for i in range(0, len(unique_rows), batch_size):
            batch = unique_rows[i : i + batch_size]
            try:
                result = (
                    db.table("tenders")
                    .upsert(batch, on_conflict=on_conflict)
                    .execute()
                )
                count = len(result.data) if result.data else 0
                total += count
            except Exception as e:
                logger.error(f"Upsert batch {i // batch_size} failed: {e}")

        logger.info(f"Upserted {total} tenders (from {len(unique_rows)} unique)")
        return total

    def fetch_existing_by_registry(
        self,
        registry_numbers: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not registry_numbers:
            return {}

        db = self._get_client()
        result_map: dict[str, dict[str, Any]] = {}

        # Supabase has URL length limits, batch the lookups
        batch_size = 50
        for i in range(0, len(registry_numbers), batch_size):
            batch = registry_numbers[i : i + batch_size]
            try:
                result = (
                    db.table("tenders")
                    .select("*")
                    .in_("registry_number", batch)
                    .execute()
                )
                for row in result.data or []:
                    reg = row.get("registry_number")
                    if reg:
                        result_map[reg] = row
            except Exception as e:
                logger.error(f"Fetch existing batch failed: {e}")

        return result_map

    def fetch_record_by_id(self, record_id: str) -> Optional[dict[str, Any]]:
        db = self._get_client()
        try:
            result = db.table("tenders").select("*").eq("id", record_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Fetch record {record_id} failed: {e}")
            return None

    def update_record(self, record_id: str, updates: dict[str, Any]) -> bool:
        db = self._get_client()
        try:
            db.table("tenders").update(updates).eq("id", record_id).execute()
            return True
        except Exception as e:
            logger.error(f"Update record {record_id} failed: {e}")
            return False

    def store_snapshot(
        self,
        registry_number: str,
        source_platform: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Store raw snapshot for audit trail.

        Uses tender_snapshots table if exists, otherwise stores in raw_data field.
        """
        db = self._get_client()
        try:
            # Try dedicated snapshots table first
            db.table("tender_snapshots").insert({
                "registry_number": registry_number,
                "source_platform": source_platform,
                "snapshot_data": snapshot,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            # Fallback: store in raw_data field of tender record
            try:
                db.table("tenders").update({
                    "raw_data": snapshot,
                }).eq("registry_number", registry_number).eq(
                    "source_platform", source_platform
                ).execute()
            except Exception as e:
                logger.debug(f"Snapshot storage failed for {registry_number}: {e}")
