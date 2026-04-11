"""Full tender normalization: transform ParsedRecord → TenderCreate-compatible dict."""

from __future__ import annotations

from typing import Any, Optional

from engine.parsers.utils import (
    parse_price,
    parse_date,
    parse_registry_number,
    clean_text,
    normalize_region,
)
from engine.normalizers.law_type import detect_law_type
from engine.normalizers.purchase_method import normalize_purchase_method
from engine.types import ParsedRecord, SourceCategory
from engine.observability.logger import get_logger

logger = get_logger("normalizer.tender")


class TenderNormalizer:
    """Normalize parsed records into canonical TenderCreate-compatible dicts.

    This is the single place where field mapping, validation, and cleanup happens.
    """

    MAX_TITLE_LENGTH = 500

    def normalize(self, record: ParsedRecord) -> dict[str, Any] | None:
        """Normalize a ParsedRecord to a canonical tender dict.

        Returns None if record is invalid (no title).
        """
        title = clean_text(record.title, max_length=self.MAX_TITLE_LENGTH)
        if not title:
            return None

        source_platform = record.source_id

        registry_number = record.registry_number or parse_registry_number(
            record.title or "", record.original_url or ""
        )

        law_type = record.law_type or detect_law_type(
            registry_number=registry_number,
            source_platform=source_platform,
            title=title,
            description=record.description or "",
        )

        purchase_method = normalize_purchase_method(record.purchase_method)
        customer_region = normalize_region(record.customer_region)

        nmck = record.nmck
        if isinstance(nmck, str):
            nmck = parse_price(nmck)
        elif isinstance(nmck, (int, float)):
            nmck = float(nmck) if nmck > 0 else None

        publish_date = record.publish_date
        if isinstance(publish_date, str):
            publish_date = parse_date(publish_date)

        submission_deadline = record.submission_deadline
        if isinstance(submission_deadline, str):
            submission_deadline = parse_date(submission_deadline)

        auction_date = record.auction_date
        if isinstance(auction_date, str):
            auction_date = parse_date(auction_date)

        return {
            "source_platform": source_platform,
            "registry_number": registry_number,
            "law_type": law_type,
            "purchase_method": purchase_method,
            "title": title,
            "description": clean_text(record.description, max_length=2000),
            "customer_name": clean_text(record.customer_name, max_length=300),
            "customer_inn": record.customer_inn,
            "customer_region": customer_region,
            "okpd2_codes": record.okpd2_codes or [],
            "nmck": nmck,
            "currency": "RUB",
            "publish_date": publish_date,
            "submission_deadline": submission_deadline,
            "auction_date": auction_date,
            "status": record.status or "active",
            "documents_urls": record.documents_urls or [],
            "contact_info": record.contact_info or {},
            "original_url": record.original_url or "",
            "raw_data": record.raw_data,
            "niche_tags": [],
        }

    def normalize_batch(self, records: list[ParsedRecord]) -> list[dict[str, Any]]:
        """Normalize a batch, filtering out invalid records."""
        results = []
        for record in records:
            try:
                normalized = self.normalize(record)
                if normalized:
                    results.append(normalized)
            except Exception as e:
                logger.warning(
                    f"Normalization failed for {record.source_id}: {e}"
                )
        return results
