"""Niche tagging for tenders/auctions.

Uses OKPD2 code prefixes and keyword matching — same logic as pipeline/tagger.py
but works on dicts instead of Pydantic models (compatible with engine pipeline).
"""

from __future__ import annotations

from typing import Any

from shared.config import ALL_NICHES, NichePreset
from engine.observability.logger import get_logger

logger = get_logger("pipeline.tagger")


class NicheTagger:
    """Tag records with niche categories based on OKPD2 codes and keywords."""

    def __init__(self, niches: list[NichePreset] | None = None):
        self._niches = niches or ALL_NICHES

    def tag(self, record: dict[str, Any]) -> list[str]:
        """Determine niche tags for a record dict.

        Checks:
        1. OKPD2 code prefix matches
        2. Keyword matches in title + description
        """
        tags: list[str] = []
        text = f"{record.get('title', '')} {record.get('description', '')}".lower()
        okpd2_codes = record.get("okpd2_codes") or []

        for niche in self._niches:
            matched = False

            # Check OKPD2 prefixes
            for code in okpd2_codes:
                for prefix in niche.okpd2_prefixes:
                    if code.startswith(prefix):
                        matched = True
                        break
                if matched:
                    break

            # Check keywords
            if not matched:
                for keyword in niche.keywords:
                    if keyword.lower() in text:
                        matched = True
                        break

            if matched:
                tags.append(niche.tag)

        return sorted(tags)

    def tag_batch(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Tag a batch of records in place."""
        tagged_count = 0
        for record in records:
            record["niche_tags"] = self.tag(record)
            if record["niche_tags"]:
                tagged_count += 1

        logger.info(f"Tagged {tagged_count}/{len(records)} records")
        return records
