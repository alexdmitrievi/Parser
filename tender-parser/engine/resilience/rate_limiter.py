"""Per-source rate limiter with token bucket algorithm."""

from __future__ import annotations

import asyncio
import time
import random
import threading


class RateLimiter:
    """Token bucket rate limiter. Thread-safe for sync, also usable in async."""

    def __init__(self, min_delay: float = 2.0, max_delay: float = 6.0, max_concurrent: int = 1):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        self._semaphore = threading.Semaphore(max_concurrent)
        self._async_semaphore: asyncio.Semaphore | None = None

    def _get_delay(self) -> float:
        return random.uniform(self.min_delay, self.max_delay)

    def wait(self) -> None:
        """Block until rate limit allows next request (sync)."""
        self._semaphore.acquire()
        try:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_request_at
                delay = self._get_delay()
                if elapsed < delay:
                    time.sleep(delay - elapsed)
                self._last_request_at = time.monotonic()
        finally:
            self._semaphore.release()

    async def async_wait(self) -> None:
        """Async version of wait()."""
        if self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(self.max_concurrent)

        async with self._async_semaphore:
            now = time.monotonic()
            with self._lock:
                elapsed = now - self._last_request_at
                delay = self._get_delay()
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            with self._lock:
                self._last_request_at = time.monotonic()
