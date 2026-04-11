"""Source registry: registers, discovers, and provides source configurations.

Sources can be registered:
1. Programmatically via register()
2. From YAML configs (future)

The registry is the single source of truth for what sources exist and how they're configured.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Type

from engine.types import SourceConfig, SourceCategory, FetchMethod, RateLimitConfig, RetryConfig
from engine.observability.logger import get_logger

logger = get_logger("config.registry")


class SourceRegistry:
    """Central registry of all source adapters and their configurations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[str, SourceConfig] = {}
        self._adapter_classes: dict[str, type] = {}

    def register(
        self,
        config: SourceConfig,
        adapter_class: type | None = None,
    ) -> None:
        """Register a source configuration and optional adapter class."""
        with self._lock:
            self._configs[config.source_id] = config
            if adapter_class:
                self._adapter_classes[config.source_id] = adapter_class
            logger.debug(f"Registered source: {config.source_id} ({config.category.value})")

    def get_config(self, source_id: str) -> SourceConfig | None:
        with self._lock:
            return self._configs.get(source_id)

    def get_adapter_class(self, source_id: str) -> type | None:
        with self._lock:
            return self._adapter_classes.get(source_id)

    def list_sources(
        self,
        category: SourceCategory | None = None,
        enabled_only: bool = True,
    ) -> list[SourceConfig]:
        """List registered sources, optionally filtered."""
        with self._lock:
            configs = list(self._configs.values())

        if category:
            configs = [c for c in configs if c.category == category]
        if enabled_only:
            configs = [c for c in configs if c.enabled]
        return configs

    def list_source_ids(
        self,
        category: SourceCategory | None = None,
        enabled_only: bool = True,
    ) -> list[str]:
        return [c.source_id for c in self.list_sources(category, enabled_only)]

    def has_source(self, source_id: str) -> bool:
        with self._lock:
            return source_id in self._configs

    def disable_source(self, source_id: str) -> None:
        with self._lock:
            if source_id in self._configs:
                self._configs[source_id].enabled = False
                logger.info(f"Disabled source: {source_id}")

    def enable_source(self, source_id: str) -> None:
        with self._lock:
            if source_id in self._configs:
                self._configs[source_id].enabled = True


# Singleton
_registry: SourceRegistry | None = None


def get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry


# ─────────────────────── Convenience factory ───────────────────────


def make_config(
    source_id: str,
    platform_name: str,
    base_url: str,
    category: SourceCategory = SourceCategory.TENDERS,
    fetch_method: FetchMethod = FetchMethod.HTTP,
    search_queries: list[str] | None = None,
    max_pages: int = 3,
    selectors: dict[str, str] | None = None,
    endpoints: dict[str, str] | None = None,
    min_delay: float = 2.0,
    max_delay: float = 6.0,
    max_concurrent: int = 1,
    law_type_default: str = "commercial",
    use_proxy: bool = False,
    wait_selector: str = "",
    enabled: bool = True,
    **kwargs: Any,
) -> SourceConfig:
    """Convenience factory for SourceConfig."""
    return SourceConfig(
        source_id=source_id,
        platform_name=platform_name,
        category=category,
        base_url=base_url,
        fetch_method=fetch_method,
        search_queries=search_queries or [],
        max_pages=max_pages,
        selectors=selectors or {},
        endpoints=endpoints or {},
        rate_limit=RateLimitConfig(
            min_delay=min_delay,
            max_delay=max_delay,
            max_concurrent=max_concurrent,
        ),
        retry=RetryConfig(),
        law_type_default=law_type_default,
        enabled=enabled,
        use_proxy=use_proxy,
        wait_selector=wait_selector,
        **kwargs,
    )
