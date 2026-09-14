"""Enhanced deduplication with source priority."""

from __future__ import annotations

from typing import Any

from engine.types import CrawlAction
from engine.observability.logger import get_logger

logger = get_logger("pipeline.dedup")

# Priority list: lower index = higher priority
SOURCE_PRIORITY = (
    "eis", "eis_ftp", "eis_api",
    "roseltorg", "sberbank_ast", "rts_tender", "tektorg",
    "gazprom", "rosatom", "rosneft", "lukoil", "nornickel", "mts",
    "b2b_center", "fabrikant", "tenderpro", "rostender", "tenderguru",
    "lot_online", "torgi_gov",
    "corpmsp", "frprf", "mspbank", "mybusiness",
)


def _priority(platform: str) -> int:
    try:
        return SOURCE_PRIORITY.index(platform)
    except ValueError:
        return len(SOURCE_PRIORITY)


class Deduplicator:
    """Check if a record should be inserted, updated, or skipped.

    Uses registry_number as the natural key for dedup.
    When both old and new exist, prefers fields from the higher-priority source.
    """

    def check(
        self,
        incoming: dict[str, Any],
        existing_map: dict[str, dict[str, Any]],
    ) -> CrawlAction:
        """Determine action for an incoming record.

        Args:
            incoming: Normalized record to process
            existing_map: {registry_number: existing_record}

        Returns:
            CrawlAction.INSERT, UPDATE, or SKIP
        """
        reg = incoming.get("registry_number")
        if not reg:
            # No registry number — always insert (will be deduped by DB upsert)
            return CrawlAction.INSERT

        existing = existing_map.get(reg)
        if not existing:
            return CrawlAction.INSERT

        # Merge: prefer incoming if it has higher/equal priority
        in_src = incoming.get("source_platform", "")
        ex_src = existing.get("source_platform", "")

        if _priority(in_src) <= _priority(ex_src):
            # Incoming has higher priority — update
            self._merge_fields(incoming, existing)
            return CrawlAction.UPDATE
        else:
            # Existing has higher priority — fill in missing fields from incoming
            self._merge_fields(incoming, existing, reverse=True)
            return CrawlAction.UPDATE

    def _merge_fields(
        self,
        primary: dict[str, Any],
        secondary: dict[str, Any],
        reverse: bool = False,
    ) -> None:
        """Fill empty fields in primary from secondary.

        If reverse=True, fill primary from secondary (incoming gets enriched).
        """
        src = secondary if not reverse else primary
        dst = primary if not reverse else secondary

        for key, value in src.items():
            if key in ("id", "created_at", "updated_at", "source_platform"):
                continue
            if value in (None, "", [], {}):
                continue
            if dst.get(key) in (None, "", [], {}):
                dst[key] = value

        # Accumulate sources
        sources = list(dict.fromkeys(
            (primary.get("sources") or [])
            + (secondary.get("sources") or [])
            + [primary.get("source_platform", ""), secondary.get("source_platform", "")]
        ))
        primary["sources"] = [s for s in sources if s]
