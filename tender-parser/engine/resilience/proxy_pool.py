"""Proxy pool with rotation and failure tracking."""

from __future__ import annotations

import os
import random
import threading
from dataclasses import dataclass, field

from engine.observability.logger import get_logger

logger = get_logger("proxy_pool")


@dataclass
class ProxyEntry:
    url: str
    failures: int = 0
    total_uses: int = 0
    enabled: bool = True


class ProxyPool:
    """Manages a pool of proxies with rotation and health tracking.

    Proxies loaded from PROXY_LIST env var (comma-separated) or added programmatically.
    Format: protocol://user:pass@host:port or protocol://host:port
    """

    MAX_FAILURES = 5  # disable after N consecutive failures

    def __init__(self, proxies: list[str] | None = None):
        self._lock = threading.Lock()
        self._proxies: list[ProxyEntry] = []
        self._index = 0

        # Load from env if not provided
        if proxies is None:
            env_proxies = os.environ.get("PROXY_LIST", "")
            if env_proxies:
                proxies = [p.strip() for p in env_proxies.split(",") if p.strip()]

        if proxies:
            for p in proxies:
                self._proxies.append(ProxyEntry(url=p))
            logger.info(f"Proxy pool initialized with {len(self._proxies)} proxies")

    @property
    def has_proxies(self) -> bool:
        return len(self._proxies) > 0

    def get_proxy(self) -> str | None:
        """Get next available proxy (round-robin with skip of disabled)."""
        if not self._proxies:
            return None

        with self._lock:
            available = [p for p in self._proxies if p.enabled]
            if not available:
                # Reset all proxies if all disabled
                for p in self._proxies:
                    p.enabled = True
                    p.failures = 0
                available = self._proxies
                logger.warning("All proxies were disabled, resetting pool")

            # Round-robin
            proxy = available[self._index % len(available)]
            self._index += 1
            proxy.total_uses += 1
            return proxy.url

    def get_random_proxy(self) -> str | None:
        """Get a random available proxy."""
        if not self._proxies:
            return None

        with self._lock:
            available = [p for p in self._proxies if p.enabled]
            if not available:
                return None
            choice = random.choice(available)
            choice.total_uses += 1
            return choice.url

    def report_success(self, proxy_url: str) -> None:
        with self._lock:
            for p in self._proxies:
                if p.url == proxy_url:
                    p.failures = 0
                    break

    def report_failure(self, proxy_url: str) -> None:
        with self._lock:
            for p in self._proxies:
                if p.url == proxy_url:
                    p.failures += 1
                    if p.failures >= self.MAX_FAILURES:
                        p.enabled = False
                        logger.warning(f"Proxy disabled: {proxy_url} ({p.failures} failures)")
                    break

    def get_stats(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "url": p.url[:20] + "...",  # hide full URL
                    "enabled": p.enabled,
                    "failures": p.failures,
                    "total_uses": p.total_uses,
                }
                for p in self._proxies
            ]


_pool: ProxyPool | None = None


def get_proxy_pool() -> ProxyPool:
    global _pool
    if _pool is None:
        _pool = ProxyPool()
    return _pool
