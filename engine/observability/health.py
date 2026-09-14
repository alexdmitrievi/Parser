"""Source health tracking with state machine."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from engine.types import SourceHealth


@dataclass
class SourceStatus:
    health: SourceHealth = SourceHealth.UNKNOWN
    last_check_at: float = 0.0
    last_success_at: float = 0.0
    last_error: str = ""
    consecutive_failures: int = 0
    cooldown_until: float = 0.0  # timestamp when source can be retried

    def is_available(self) -> bool:
        if self.health == SourceHealth.DOWN:
            return time.time() >= self.cooldown_until
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "health": self.health.value,
            "last_check_at": self.last_check_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "cooldown_until": self.cooldown_until,
            "available": self.is_available(),
        }


class HealthTracker:
    """Track health state per source with automatic cooldown."""

    # After this many consecutive failures, mark DOWN
    FAILURE_THRESHOLD = 3
    # Cooldown durations (seconds) by consecutive failure count
    COOLDOWN_LADDER = [60, 300, 900, 3600]  # 1m, 5m, 15m, 1h

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: dict[str, SourceStatus] = {}

    def _get(self, source_id: str) -> SourceStatus:
        if source_id not in self._sources:
            self._sources[source_id] = SourceStatus()
        return self._sources[source_id]

    def record_success(self, source_id: str) -> None:
        with self._lock:
            s = self._get(source_id)
            s.health = SourceHealth.HEALTHY
            s.last_check_at = time.time()
            s.last_success_at = time.time()
            s.consecutive_failures = 0
            s.cooldown_until = 0.0
            s.last_error = ""

    def record_failure(self, source_id: str, error: str) -> None:
        with self._lock:
            s = self._get(source_id)
            s.last_check_at = time.time()
            s.last_error = error
            s.consecutive_failures += 1

            if s.consecutive_failures >= self.FAILURE_THRESHOLD:
                s.health = SourceHealth.DOWN
                idx = min(
                    s.consecutive_failures - self.FAILURE_THRESHOLD,
                    len(self.COOLDOWN_LADDER) - 1,
                )
                s.cooldown_until = time.time() + self.COOLDOWN_LADDER[idx]
            else:
                s.health = SourceHealth.DEGRADED

    def is_available(self, source_id: str) -> bool:
        with self._lock:
            return self._get(source_id).is_available()

    def get_status(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            return self._get(source_id).to_dict()

    def get_all_statuses(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {sid: s.to_dict() for sid, s in self._sources.items()}


_tracker: HealthTracker | None = None


def get_health_tracker() -> HealthTracker:
    global _tracker
    if _tracker is None:
        _tracker = HealthTracker()
    return _tracker
