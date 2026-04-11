"""In-process metrics collection for crawl operations.

Lightweight — stores counters in memory, can be queried via API or logged.
No external dependency (Prometheus/StatsD) required — can be added later.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceMetrics:
    """Per-source accumulated metrics."""
    total_runs: int = 0
    total_fetches: int = 0
    total_fetch_errors: int = 0
    total_parsed: int = 0
    total_parse_errors: int = 0
    total_inserted: int = 0
    total_updated: int = 0
    total_skipped: int = 0
    last_run_at: float = 0.0
    last_run_duration_ms: float = 0.0
    last_success_rate: float = 0.0
    consecutive_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "total_fetches": self.total_fetches,
            "total_fetch_errors": self.total_fetch_errors,
            "total_parsed": self.total_parsed,
            "total_parse_errors": self.total_parse_errors,
            "total_inserted": self.total_inserted,
            "total_updated": self.total_updated,
            "total_skipped": self.total_skipped,
            "last_run_at": self.last_run_at,
            "last_run_duration_ms": self.last_run_duration_ms,
            "last_success_rate": self.last_success_rate,
            "consecutive_failures": self.consecutive_failures,
        }


class MetricsCollector:
    """Thread-safe metrics store for all sources."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: dict[str, SourceMetrics] = defaultdict(SourceMetrics)

    def _get(self, source_id: str) -> SourceMetrics:
        return self._sources[source_id]

    def record_run_start(self, source_id: str) -> None:
        with self._lock:
            m = self._get(source_id)
            m.total_runs += 1
            m.last_run_at = time.time()

    def record_fetch(self, source_id: str, success: bool) -> None:
        with self._lock:
            m = self._get(source_id)
            m.total_fetches += 1
            if not success:
                m.total_fetch_errors += 1

    def record_parse(self, source_id: str, count: int, errors: int = 0) -> None:
        with self._lock:
            m = self._get(source_id)
            m.total_parsed += count
            m.total_parse_errors += errors

    def record_persist(self, source_id: str, inserted: int, updated: int, skipped: int) -> None:
        with self._lock:
            m = self._get(source_id)
            m.total_inserted += inserted
            m.total_updated += updated
            m.total_skipped += skipped

    def record_run_end(self, source_id: str, duration_ms: float, success_rate: float) -> None:
        with self._lock:
            m = self._get(source_id)
            m.last_run_duration_ms = duration_ms
            m.last_success_rate = success_rate
            if success_rate > 0:
                m.consecutive_failures = 0
            else:
                m.consecutive_failures += 1

    def get_source_metrics(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            return self._get(source_id).to_dict()

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {sid: m.to_dict() for sid, m in self._sources.items()}


# Singleton
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
