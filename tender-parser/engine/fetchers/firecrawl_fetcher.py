"""Firecrawl-backed fetcher for Cloudflare-protected lead sources.

Some lead directories (e.g. all.biz) sit behind Cloudflare and refuse
requests from datacenter IPs — which is exactly what the VM and GitHub
Actions runners have. :class:`FirecrawlFetcher` fetches those pages through
the Firecrawl API, which renders JavaScript from its own clean IPs and
returns real content instead of a challenge page.

This is opt-in, not a silent policy change: the fetcher is only used for
sources the owner has explicitly listed in ``LEADS_FIRECRAWL_SOURCES`` and
only when ``FIRECRAWL_API_KEY`` is set. Every other lead source keeps the
polite, self-identifying transport. See ``docs/SCRAPING_POLICY.md``.

Interface mirrors :class:`~engine.fetchers.polite_fetcher.PoliteFetcher` so
the leads adapters and :class:`~engine.fetchers.robots.RobotsGate` can swap
it in without changes: ``fetch() -> PoliteResponse``, ``user_agent``,
``close()`` and the context-manager protocol.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from engine.fetchers.polite_fetcher import PoliteResponse, SourceBlocked
from engine.observability.logger import get_logger
from engine.resilience.rate_limiter import RateLimiter
from engine.resilience.retry_policy import with_retry
from engine.types import RetryConfig

logger = get_logger("fetcher.firecrawl")

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

# Firecrawl API-level failures we will not work around.
_FIRECRAWL_FATAL_STATUS = (401, 402, 403)


class FirecrawlFetcher:
    """Fetch pages through the Firecrawl scrape API.

    Args:
        api_key: Firecrawl API key (``fc-...``). Required.
        rate_limiter: Shared polite rate limiter; defaults to a slow one.
        retry_config: Transport retry policy (backoff on 429/5xx).
        timeout: HTTP timeout for the Firecrawl API call itself.
        source_id: Identifier used in logs.
        user_agent: Honest crawler identity, kept for the RobotsGate token.
    """

    def __init__(
        self,
        api_key: str,
        rate_limiter: RateLimiter | None = None,
        retry_config: RetryConfig | None = None,
        timeout: float = 60.0,
        source_id: str = "leads",
        user_agent: str = "",
    ) -> None:
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY is required")
        self._api_key = api_key
        self.source_id = source_id
        self.user_agent = user_agent or "TenderProLeadsBot/1.0 (via Firecrawl)"
        self._rate_limiter = rate_limiter or RateLimiter(min_delay=6.0, max_delay=8.0)
        # Firecrawl has a low requests/min ceiling on small plans; keep a
        # floor of 6s between calls so bursts in discover() don't trigger 429.
        if self._rate_limiter.min_delay < 6.0:
            self._rate_limiter.min_delay = 6.0
            self._rate_limiter.max_delay = max(self._rate_limiter.max_delay, 8.0)
        self._retry_config = retry_config or RetryConfig()
        self._timeout = timeout
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def fetch(self, url: str, *, raise_on_block: bool = True, **kwargs: Any) -> PoliteResponse:
        """Scrape ``url`` through Firecrawl and return it as a ``PoliteResponse``.

        Transport failures and Firecrawl 429/5xx are retried with backoff.
        Firecrawl 401/402/403 (bad key / out of credits / forbidden) raise
        :class:`SourceBlocked` immediately. A target page that itself answers
        403 surfaces as a non-ok response with that status code.

        Raises:
            SourceBlocked: Firecrawl refused the request, or (when
                ``raise_on_block``) the target page answered 401/403.
            RetryExhausted: Transport failures outlasted the retry budget.
        """
        self._rate_limiter.wait()
        start = time.monotonic()

        def _call() -> PoliteResponse:
            resp = self._get_client().post(
                FIRECRAWL_SCRAPE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "url": url,
                    "formats": ["rawHtml", "markdown"],
                    "onlyMainContent": False,
                    "waitFor": 0,
                },
            )

            if resp.status_code in _FIRECRAWL_FATAL_STATUS:
                detail = resp.text[:200] if resp.text else ""
                raise SourceBlocked(url, f"Firecrawl API {resp.status_code} — {detail}", resp.status_code)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Firecrawl API {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )

            try:
                payload = resp.json()
            except ValueError as e:
                raise httpx.DecodingError(f"Firecrawl returned non-JSON: {e}") from e

            data = payload.get("data") or {}
            meta = data.get("metadata") or {}
            text = data.get("rawHtml") or data.get("html") or data.get("markdown") or ""
            final_url = meta.get("url") or url
            status = int(meta.get("statusCode") or (200 if payload.get("success") else resp.status_code))
            return PoliteResponse(url=final_url, status_code=status, text=text, headers={})

        result = with_retry(_call, config=self._retry_config, source_id=self.source_id)()
        result.elapsed_ms = (time.monotonic() - start) * 1000

        if raise_on_block and result.status_code in (401, 403):
            raise SourceBlocked(url, f"HTTP {result.status_code} via Firecrawl", result.status_code)
        return result

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

    def __enter__(self) -> FirecrawlFetcher:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


__all__ = ["FirecrawlFetcher", "FIRECRAWL_SCRAPE_URL"]
