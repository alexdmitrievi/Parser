"""Pipeline orchestrator: coordinates fetch → parse → normalize → dedup → persist.

This is the single entry point for running a source through the full pipeline.
Integrates all layers: fetchers, parsers, normalizers, dedup, persistence, observability.
"""

from __future__ import annotations

import time
from typing import Any

from engine.types import (
    SourceConfig, SourceCategory, FetchMethod, FetchResult,
    ParsedRecord, CrawlStats, CrawlAction,
)
from engine.normalizers.tender_normalizer import TenderNormalizer
from engine.pipeline.deduplicator import Deduplicator
from engine.pipeline.tagger import NicheTagger
from engine.pipeline.versioner import ChangeDetector
from engine.persistence.supabase_repo import SupabaseTenderRepository
from engine.observability.logger import CrawlLogger, new_correlation_id
from engine.observability.metrics import get_metrics
from engine.observability.health import get_health_tracker
from engine.resilience.circuit_breaker import CircuitBreaker


class PipelineOrchestrator:
    """Runs a source through the full ingestion pipeline.

    Usage:
        orchestrator = PipelineOrchestrator()
        stats = orchestrator.run_source(source_adapter)
    """

    def __init__(
        self,
        repository: SupabaseTenderRepository | None = None,
        normalizer: TenderNormalizer | None = None,
        tagger: NicheTagger | None = None,
        deduplicator: Deduplicator | None = None,
        change_detector: ChangeDetector | None = None,
    ):
        self._repo = repository or SupabaseTenderRepository()
        self._normalizer = normalizer or TenderNormalizer()
        self._tagger = tagger or NicheTagger()
        self._dedup = deduplicator or Deduplicator()
        self._change_detector = change_detector or ChangeDetector()
        self._metrics = get_metrics()
        self._health = get_health_tracker()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def _get_circuit_breaker(self, source_id: str) -> CircuitBreaker:
        if source_id not in self._circuit_breakers:
            self._circuit_breakers[source_id] = CircuitBreaker(source_id)
        return self._circuit_breakers[source_id]

    def run_source(self, source) -> CrawlStats:
        """Run a full pipeline for a source adapter.

        Args:
            source: Any object implementing the SourceAdapter protocol.

        Returns:
            CrawlStats with counts and timing.
        """
        source_id = source.source_id
        cid = new_correlation_id()
        log = CrawlLogger(source_id)
        stats = CrawlStats(source_id=source_id)

        # Check circuit breaker
        cb = self._get_circuit_breaker(source_id)
        if not cb.allow_request():
            log.warning("Circuit breaker OPEN — skipping source")
            return stats

        # Check health tracker
        if not self._health.is_available(source_id):
            log.warning("Source in cooldown — skipping")
            return stats

        self._metrics.record_run_start(source_id)
        start_time = time.monotonic()
        log.info("Pipeline started")

        try:
            # Step 1: Discover URLs to scrape
            urls = source.discover()
            log.info(f"Discovered {len(urls)} target URLs")

            # Step 2: Fetch + Parse each URL
            all_parsed: list[ParsedRecord] = []
            for url in urls:
                try:
                    fetch_result = source.fetch_page(url)
                    stats.total_fetched += 1
                    self._metrics.record_fetch(source_id, success=True)
                    log.fetch_ok(url, fetch_result.elapsed_ms)

                    records = source.parse_listing(fetch_result)
                    stats.total_parsed += len(records)
                    self._metrics.record_parse(source_id, len(records))
                    log.parse_ok(len(records), url)

                    all_parsed.extend(records)

                    if not records:
                        break  # No more results on this page

                except Exception as e:
                    stats.fetch_errors += 1
                    self._metrics.record_fetch(source_id, success=False)
                    log.fetch_fail(url, str(e))
                    continue

            if not all_parsed:
                log.warning("No records parsed — nothing to process")
                cb.record_failure()
                self._health.record_failure(source_id, "No records parsed")
                stats.finished_at = __import__("datetime").datetime.utcnow()
                return stats

            # Step 3: Normalize
            normalized = self._normalizer.normalize_batch(all_parsed)
            log.info(f"Normalized {len(normalized)} records (from {len(all_parsed)} parsed)")

            # Step 4: Tag
            for record in normalized:
                record["niche_tags"] = self._tagger.tag(record)

            # Step 5: Dedup against existing
            registry_numbers = [
                r["registry_number"] for r in normalized
                if r.get("registry_number")
            ]
            existing = self._repo.fetch_existing_by_registry(registry_numbers)

            to_upsert: list[dict[str, Any]] = []
            for record in normalized:
                action = self._dedup.check(record, existing)
                if action == CrawlAction.INSERT:
                    stats.inserted += 1
                    to_upsert.append(record)
                elif action == CrawlAction.UPDATE:
                    stats.updated += 1
                    # Check for changes
                    reg = record.get("registry_number", "")
                    if reg and reg in existing:
                        changes = self._change_detector.detect_changes(existing[reg], record)
                        if changes:
                            log.debug(f"Changes for {reg}: {list(changes.keys())}")
                    to_upsert.append(record)
                else:
                    stats.skipped += 1

            # Step 6: Persist
            if to_upsert:
                saved = self._repo.upsert_batch(to_upsert)
                log.info(f"Persisted {saved} records")

            # Record success
            cb.record_success()
            self._health.record_success(source_id)

        except Exception as e:
            stats.errors += 1
            cb.record_failure()
            self._health.record_failure(source_id, str(e))
            log.error(f"Pipeline failed: {e}")

        # Finalize stats
        elapsed = (time.monotonic() - start_time) * 1000
        stats.duration_ms = elapsed
        stats.finished_at = __import__("datetime").datetime.utcnow()
        self._metrics.record_run_end(source_id, elapsed, stats.success_rate)
        self._metrics.record_persist(
            source_id, stats.inserted, stats.updated, stats.skipped
        )

        log.pipeline_result(stats.inserted, stats.updated, stats.skipped, stats.errors)
        log.info(f"Pipeline finished in {elapsed:.0f}ms")

        return stats

    def run_sources(self, sources: list, parallel: bool = False) -> list[CrawlStats]:
        """Run multiple sources sequentially (parallel=True reserved for future)."""
        all_stats: list[CrawlStats] = []
        for source in sources:
            try:
                stats = self.run_source(source)
                all_stats.append(stats)
            except Exception as e:
                log = CrawlLogger(getattr(source, "source_id", "unknown"))
                log.error(f"Source runner failed: {e}")
        return all_stats
