"""Protocols and interfaces for all engine layers.

Every component in the engine communicates through these typed contracts.
No implementation details leak across boundaries.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable


# ─────────────────────── Enums ───────────────────────


class SourceCategory(str, enum.Enum):
    TENDERS = "tenders"
    AUCTIONS = "auctions"
    GRANTS = "grants"


class FetchMethod(str, enum.Enum):
    HTTP = "http"
    BROWSER = "browser"
    FTP = "ftp"
    API_JSON = "api_json"
    API_XML = "api_xml"


class CrawlAction(str, enum.Enum):
    INSERT = "insert"
    UPDATE = "update"
    SKIP = "skip"
    ERROR = "error"


class SourceHealth(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


# ─────────────────────── Value Objects ───────────────────────


@dataclass(frozen=True)
class FetchResult:
    """Raw payload from a fetcher."""
    url: str
    content: str | bytes
    content_type: str  # "html", "xml", "json", "binary"
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    fetch_method: FetchMethod = FetchMethod.HTTP
    elapsed_ms: float = 0.0


@dataclass
class ParsedRecord:
    """A single parsed entity before normalization.

    Source adapters populate these fields from raw HTML/XML/JSON.
    The normalizer then converts ParsedRecord → dict for persistence.
    """
    source_id: str
    title: str
    raw_data: dict[str, Any] = field(default_factory=dict)
    registry_number: str | None = None
    original_url: str = ""
    nmck: float | None = None
    customer_name: str | None = None
    customer_inn: str | None = None
    customer_region: str | None = None
    law_type: str | None = None
    purchase_method: str | None = None
    description: str | None = None
    okpd2_codes: list[str] = field(default_factory=list)
    publish_date: datetime | None = None
    submission_deadline: datetime | None = None
    auction_date: datetime | None = None
    status: str = "active"
    documents_urls: list[dict] = field(default_factory=list)
    contact_info: dict[str, Any] = field(default_factory=dict)
    category: SourceCategory = SourceCategory.TENDERS
    raw_html: str = ""  # for snapshot/audit


@dataclass
class CrawlJobResult:
    """Result of processing a single crawl job."""
    source_id: str
    action: CrawlAction
    record_id: str | None = None
    registry_number: str | None = None
    error: str | None = None
    changes: dict[str, tuple[Any, Any]] | None = None  # field -> (old, new)


@dataclass
class CrawlStats:
    """Aggregated stats for a crawl run."""
    source_id: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    total_fetched: int = 0
    total_parsed: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    fetch_errors: int = 0
    parse_errors: int = 0
    duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.total_parsed + self.errors
        return self.total_parsed / total if total > 0 else 0.0


# ─────────────────────── Protocols ───────────────────────


@runtime_checkable
class Fetcher(Protocol):
    """Fetches raw content from a URL."""

    async def fetch(self, url: str, **kwargs: Any) -> FetchResult: ...
    async def close(self) -> None: ...


@runtime_checkable
class Parser(Protocol):
    """Extracts structured records from raw content."""

    def parse(self, raw: FetchResult, source_config: dict[str, Any]) -> list[ParsedRecord]: ...


@runtime_checkable
class Normalizer(Protocol):
    """Transforms parsed records into canonical models."""

    def normalize(self, record: ParsedRecord) -> dict[str, Any] | None: ...


@runtime_checkable
class Repository(Protocol):
    """Persists canonical records to storage."""

    def upsert_batch(self, records: list[dict[str, Any]], table: str) -> int: ...
    def fetch_existing(self, registry_numbers: list[str], table: str) -> dict[str, dict[str, Any]]: ...


@runtime_checkable
class SourceAdapter(Protocol):
    """A pluggable source connector. Core contract for all sources."""

    @property
    def source_id(self) -> str:
        """Unique identifier: e.g. 'eis_api', 'gazprom', 'lot_online'."""
        ...

    @property
    def category(self) -> SourceCategory:
        """What kind of data this source provides."""
        ...

    @property
    def fetch_method(self) -> FetchMethod:
        """Primary fetch method."""
        ...

    def discover(self, **kwargs: Any) -> list[str]:
        """Return list of URLs/endpoints to scrape."""
        ...

    def fetch_page(self, url: str, **kwargs: Any) -> FetchResult:
        """Fetch a single page/endpoint."""
        ...

    def parse_listing(self, raw: FetchResult) -> list[ParsedRecord]:
        """Parse a listing page into records."""
        ...

    def parse_detail(self, raw: FetchResult) -> ParsedRecord | None:
        """Parse a detail page (optional enrichment)."""
        ...

    def get_config(self) -> SourceConfig:
        """Return this source's configuration."""
        ...


# ─────────────────────── Source Config ───────────────────────


@dataclass
class RateLimitConfig:
    min_delay: float = 2.0
    max_delay: float = 6.0
    max_concurrent: int = 1
    requests_per_minute: int = 20


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_base: float = 2.0
    backoff_max: float = 60.0
    retry_on_status: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])


@dataclass
class SourceConfig:
    """Configuration for a single source. Loaded from YAML, not hardcoded."""
    source_id: str
    platform_name: str
    category: SourceCategory
    base_url: str
    fetch_method: FetchMethod = FetchMethod.HTTP
    search_queries: list[str] = field(default_factory=list)
    max_pages: int = 3
    selectors: dict[str, str] = field(default_factory=dict)
    endpoints: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    law_type_default: str = "commercial"
    enabled: bool = True
    # Proxy
    use_proxy: bool = False
    proxy_group: str = "default"
    # Browser-specific
    wait_selector: str = ""
    block_resources: list[str] = field(default_factory=lambda: ["image", "font", "media"])
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 800})

    def get_selector(self, key: str, default: str = "") -> str:
        return self.selectors.get(key, default)
