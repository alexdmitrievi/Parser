"""Base source adapter: concrete base class implementing SourceAdapter protocol.

All source adapters should inherit from this class.
It wires together: fetcher + parser + config → discover/fetch_page/parse_listing.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

from engine.types import (
    SourceConfig, FetchMethod, FetchResult, ParsedRecord,
)
from engine.fetchers.http_fetcher import HttpFetcher
from engine.parsers.html_parser import HtmlExtractor
from engine.parsers.utils import parse_price, parse_date, clean_text
from engine.resilience.rate_limiter import RateLimiter
from engine.observability.logger import CrawlLogger


class BaseSourceAdapter:
    """Base class for all source adapters.

    Subclass must override:
        - parse_listing(fetch_result) → list[ParsedRecord]

    May override:
        - discover() → custom URL generation
        - fetch_page(url) → custom fetch logic (e.g., browser)
    """

    config: SourceConfig

    def __init__(self, config: SourceConfig):
        self.config = config
        self._fetcher: HttpFetcher | None = None
        self._rate_limiter = RateLimiter(
            min_delay=config.rate_limit.min_delay if config.rate_limit else 1.0,
            max_delay=config.rate_limit.max_delay if config.rate_limit else 3.0,
        )
        self._log = CrawlLogger(config.source_id)

    @property
    def source_id(self) -> str:
        return self.config.source_id

    @property
    def platform(self) -> str:
        return self.config.platform_name

    def _get_fetcher(self) -> HttpFetcher:
        if self._fetcher is None:
            self._fetcher = HttpFetcher(
                rate_limiter=self._rate_limiter,
                default_headers=self.config.headers or {},
            )
        return self._fetcher

    # --------------- Discovery ---------------

    def discover(self) -> list[str]:
        """Build list of URLs to scrape.

        Default: generate search URLs from config.search_queries × config.max_pages.
        Override for more complex discovery (sitemap, API pagination tokens, etc.).
        """
        urls: list[str] = []
        base = self.config.base_url.rstrip("/")
        search_path = (self.config.endpoints or {}).get("search", "/search")
        query_param = (self.config.endpoints or {}).get("query_param", "q")
        page_param = (self.config.endpoints or {}).get("page_param", "page")
        queries = self.config.search_queries or [""]
        max_pages = self.config.max_pages or 2

        for query in queries:
            for page in range(1, max_pages + 1):
                params: dict[str, str] = {}
                if query:
                    params[query_param] = query
                params[page_param] = str(page)
                url = f"{base}{search_path}?{urlencode(params)}"
                urls.append(url)

        return urls

    # --------------- Fetch ---------------

    def fetch_page(self, url: str) -> FetchResult:
        """Fetch a page via HTTP. Override for browser-based sources."""
        fetcher = self._get_fetcher()
        start = time.monotonic()
        response = fetcher.fetch(url)
        elapsed = (time.monotonic() - start) * 1000

        return FetchResult(
            url=url,
            status_code=response.status_code,
            content=response.text,
            content_type=response.headers.get("content-type", ""),
            elapsed_ms=elapsed,
        )

    # --------------- Parse ---------------

    def parse_listing(self, result: FetchResult) -> list[ParsedRecord]:
        """Parse a fetched page into ParsedRecord list.

        MUST be overridden by subclasses.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement parse_listing()")

    # --------------- Lifecycle ---------------

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._fetcher:
            self._fetcher.__exit__(*exc)
            self._fetcher = None
