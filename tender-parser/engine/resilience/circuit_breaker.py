"""Circuit breaker: prevents repeated calls to failing sources."""

from __future__ import annotations

import time
import threading
from enum import Enum

from engine.observability.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject immediately
    HALF_OPEN = "half_open" # Testing if recovered


class CircuitBreaker:
    """Per-source circuit breaker.

    - CLOSED: all requests pass through
    - OPEN: requests fail immediately (after failure_threshold hits)
    - HALF_OPEN: after cooldown, allow one test request
    """

    def __init__(
        self,
        source_id: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 300.0,
        half_open_max: int = 1,
    ):
        self.source_id = source_id
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max = half_open_max

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_at = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_at >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(
                        f"Circuit {self.source_id}: OPEN -> HALF_OPEN "
                        f"(cooldown {self.cooldown_seconds}s expired)"
                    )
            return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max:
                    self._half_open_calls += 1
                    return True
            return False
        return False  # OPEN

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit {self.source_id}: HALF_OPEN -> CLOSED (success)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_at = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit {self.source_id}: HALF_OPEN -> OPEN (test failed)"
                )
            elif self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        f"Circuit {self.source_id}: CLOSED -> OPEN "
                        f"({self._failure_count} failures)"
                    )
                self._state = CircuitState.OPEN
