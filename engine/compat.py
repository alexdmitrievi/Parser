"""Compatibility bridge: connects engine adapters to existing shared/models + shared/db.

This module allows running new engine-based source adapters through the pipeline
and producing TenderCreate objects compatible with the existing `_process_and_save()` flow.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.models import TenderCreate
from engine.types import SourceConfig
from engine.sources.base import BaseSourceAdapter
from engine.pipeline.orchestrator import PipelineOrchestrator
from engine.normalizers.tender_normalizer import TenderNormalizer
from engine.pipeline.tagger import NicheTagger
from engine.observability.logger import CrawlLogger

logger = logging.getLogger(__name__)


def parsed_record_to_tender_create(record: dict[str, Any]) -> TenderCreate:
    """Convert a normalized engine dict → TenderCreate for existing DB pipeline.

    Maps engine field names 1:1 to TenderCreate fields.
    """
    return TenderCreate(
        source_platform=record.get("source_platform", ""),
        registry_number=record.get("registry_number"),
        law_type=record.get("law_type"),
        purchase_method=record.get("purchase_method"),
        title=record.get("title", ""),
        description=record.get("description"),
        customer_name=record.get("customer_name"),
        customer_inn=record.get("customer_inn"),
        customer_region=record.get("customer_region"),
        okpd2_codes=record.get("okpd2_codes") or [],
        nmck=record.get("nmck"),
        currency=record.get("currency", "RUB"),
        publish_date=record.get("publish_date"),
        submission_deadline=record.get("submission_deadline"),
        auction_date=record.get("auction_date"),
        status=record.get("status", "active"),
        documents_urls=record.get("documents_urls") or [],
        contact_info=record.get("contact_info") or {},
        original_url=record.get("original_url"),
        raw_data=record.get("raw_data"),
        niche_tags=record.get("niche_tags") or [],
    )


def run_adapter_legacy(adapter: BaseSourceAdapter) -> list[TenderCreate]:
    """Run an engine adapter and return TenderCreate objects (legacy interface).

    This bridges the gap between new engine adapters and the existing
    `_process_and_save()` flow in `scripts/run_parser.py`.

    Usage in run_parser.py:
        from engine.compat import run_adapter_legacy
        from engine.sources.tenders.corporate import get_corporate_adapter

        def run_gazprom():
            adapter = get_corporate_adapter("gazprom")
            return run_adapter_legacy(adapter)
    """
    log = CrawlLogger(adapter.source_id)
    normalizer = TenderNormalizer()
    tagger = NicheTagger()

    all_tenders: list[TenderCreate] = []

    try:
        with adapter:
            urls = adapter.discover()
            log.info(f"Discovered {len(urls)} URLs")

            for url in urls:
                try:
                    result = adapter.fetch_page(url)
                    records = adapter.parse_listing(result)

                    if not records:
                        break

                    # Normalize
                    normalized = normalizer.normalize_batch(records)

                    # Tag
                    for rec in normalized:
                        rec["niche_tags"] = tagger.tag(rec)

                    # Convert to TenderCreate
                    for rec in normalized:
                        try:
                            tender = parsed_record_to_tender_create(rec)
                            all_tenders.append(tender)
                        except Exception as e:
                            log.warning(f"Failed to convert record: {e}")

                except Exception as e:
                    log.warning(f"Error fetching {url}: {e}")
                    continue

    except Exception as e:
        log.error(f"Adapter {adapter.source_id} failed: {e}")

    log.info(f"Produced {len(all_tenders)} TenderCreate objects")
    return all_tenders


def run_adapter_full_pipeline(adapter: BaseSourceAdapter) -> dict[str, int]:
    """Run an engine adapter through the FULL pipeline (fetch → persist).

    Uses PipelineOrchestrator which handles dedup and persistence internally.
    Returns stats dict.
    """
    orch = PipelineOrchestrator()
    stats = orch.run_source(adapter)
    return {
        "source": stats.source_id,
        "fetched": stats.total_fetched,
        "parsed": stats.total_parsed,
        "inserted": stats.inserted,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "errors": stats.errors,
        "duration_ms": stats.duration_ms,
    }
