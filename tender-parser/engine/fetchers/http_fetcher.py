"""Lightweight HTTP fetcher with proxy, header rotation, and resilience hooks."""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from engine.types import FetchResult, FetchMethod, SourceConfig
from engine.resilience.rate_limiter import RateLimiter
from engine.resilience.proxy_pool import ProxyPool, get_proxy_pool
from engine.resilience.retry_policy import with_retry, RetryExhausted
from engine.observability.logger import get_logger

logger = get_logger("fetcher.http")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


class HttpFetcher:
    """HTTP fetcher with user-agent rotation, proxy support, rate limiting, and retry."""

    def __init__(
        self,
        config: SourceConfig | None = None,
        proxy_pool: ProxyPool | None = None,
        rate_limiter: RateLimiter | None = None,
        default_headers: dict[str, str] | None = None,
        user_agent: str | None = None,
    ):
        """Create a fetcher.

        Args:
            config: Source configuration (rate limit, retry, proxy, headers).
            proxy_pool: Proxy pool override.
            rate_limiter: Rate limiter override.
            default_headers: Extra headers merged into every request.
            user_agent: Pin a single User-Agent instead of rotating between
                browser strings. Used by polite crawlers that must identify
                themselves honestly. ``None`` keeps the historical rotation.
        """
        self._config = config
        self._default_headers = dict(default_headers or {})
        self._user_agent = user_agent
        self._proxy_pool = proxy_pool or get_proxy_pool()
        self._rate_limiter = rate_limiter or RateLimiter(
            min_delay=config.rate_limit.min_delay if config else 2.0,
            max_delay=config.rate_limit.max_delay if config else 6.0,
            max_concurrent=config.rate_limit.max_concurrent if config else 1,
        )
        self._client: httpx.Client | None = None
        self._source_id = config.source_id if config else "unknown"

    def _build_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": self._pick_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "DNT": "1",
        }
        if self._config and self._config.headers:
            headers.update(self._config.headers)
        if self._default_headers:
            headers.update(self._default_headers)
        if extra:
            headers.update(extra)
        return headers

    def _pick_user_agent(self) -> str:
        """Pinned UA when configured, otherwise the historical rotation."""
        return self._user_agent or random.choice(USER_AGENTS)

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            proxy_url = None
            if self._config and self._config.use_proxy and self._proxy_pool.has_proxies:
                proxy_url = self._proxy_pool.get_proxy()

            timeout = 30.0
            if self._config:
                timeout = self._config.rate_limit.min_delay * 10  # reasonable default

            self._client = httpx.Client(
                timeout=max(timeout, 30.0),
                headers=self._build_headers(),
                follow_redirects=True,
                proxy=proxy_url,
            )
        return self._client

    def fetch(self, url: str, method: str = "GET", **kwargs: Any) -> FetchResult:
        """Fetch a URL with rate limiting and retry.

        Returns FetchResult with content, status, headers.
        Raises RetryExhausted if all attempts fail.
        """
        self._rate_limiter.wait()

        start = time.monotonic()
        client = self._get_client()

        # Rotate User-Agent per request (unless one was pinned)
        client.headers["User-Agent"] = self._pick_user_agent()

        retry_config = self._config.retry if self._config else None

        def _do_fetch() -> httpx.Response:
            if method.upper() == "POST":
                return client.post(url, **kwargs)
            return client.get(url, **kwargs)

        try:
            response = with_retry(
                _do_fetch,
                config=retry_config,
                source_id=self._source_id,
            )()
            response.raise_for_status()

            elapsed = (time.monotonic() - start) * 1000
            content_type = response.headers.get("content-type", "")

            if "json" in content_type:
                ct = "json"
            elif "xml" in content_type:
                ct = "xml"
            else:
                ct = "html"

            return FetchResult(
                url=str(response.url),
                content=response.text,
                content_type=ct,
                status_code=response.status_code,
                headers=dict(response.headers),
                fetch_method=FetchMethod.HTTP,
                elapsed_ms=elapsed,
            )

        except RetryExhausted:
            raise
        except httpx.HTTPStatusError as e:
            elapsed = (time.monotonic() - start) * 1000
            return FetchResult(
                url=url,
                content="",
                content_type="error",
                status_code=e.response.status_code,
                elapsed_ms=elapsed,
            )

    def fetch_json(self, url: str, **kwargs: Any) -> FetchResult:
        """Convenience: fetch JSON API endpoint."""
        headers = kwargs.pop("headers", {})
        headers["Accept"] = "application/json"
        return self.fetch(url, headers=headers, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FetchResult:
        return self.fetch(url, method="POST", **kwargs)

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
