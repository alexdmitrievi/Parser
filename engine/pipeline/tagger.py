"""Niche tagging for tenders/auctions.

Uses OKPD2 code prefixes and keyword matching — same logic as pipeline/tagger.py
but works on dicts instead of Pydantic models (compatible with engine pipeline).
"""

from __future__ import annotations

from typing import Any

from shared.config import ALL_NICHES, NichePreset
from shared.keyword_match import any_matches, okpd2_matches
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
        text = f"{record.get('title', '')} {record.get('description', '')}"
        okpd2_codes = record.get("okpd2_codes") or []

        for niche in self._niches:
            # Keywords must start on a word boundary — otherwise short
            # abbreviations ("КТ", "ТО", "ИИ") match inside unrelated words and
            # produce junk tags. See shared/keyword_match.py.
            if okpd2_matches(okpd2_codes, niche.okpd2_prefixes) or any_matches(
                niche.keywords, text
            ):
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
