"""Polite HTTP fetcher for the leads domain.

Differs from :class:`~engine.fetchers.http_fetcher.HttpFetcher` in exactly the
ways the leads domain is required to differ:

* **Honest identity.** One pinned ``User-Agent`` naming the bot and a contact
  mailbox. No rotation between browser strings, no fingerprint spoofing.
* **No proxies.** Proxy rotation is never used, so a site that blocks us stays
  blocked instead of being circumvented.
* **Backs off on request.** ``Retry-After`` on 429/503 is honoured verbatim.
* **Stops when told to stop.** 401/403, a persistent 429, or a captcha
  challenge raises :class:`SourceBlocked`; the caller marks the source
  unavailable and moves on rather than trying to get around it.

Transport-level retries (connect errors, timeouts) reuse the shared
``engine.resilience.retry_policy`` backoff.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from engine.resilience.rate_limiter import RateLimiter
from engine.resilience.retry_policy import RetryExhausted, with_retry
from engine.types import RetryConfig
from engine.observability.logger import get_logger

logger = get_logger("fetcher.polite")

# Maximum we will ever honour from a Retry-After header. Anything longer means
# "come back another day" — we stop this run instead of sleeping through it.
MAX_RETRY_AFTER_SECONDS = 300.0

# Substrings that mark an anti-bot interstitial rather than real content.
CAPTCHA_MARKERS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "verify you are human",
    "are you a robot",
    "unusual traffic",
    "cf-browser-verification",
    "just a moment...",
    "checking your browser",
    "access denied",
    "验证码",
    "安全验证",
    "滑动验证",
    "人机验证",
    "访问被拒绝",
)

# Body is only scanned this far for captcha markers — they live in the head.
_CAPTCHA_SCAN_CHARS = 8000


class SourceBlocked(Exception):
    """The site refused us. Stop crawling it; do not attempt to evade.

    Raised on 401/403, a 429 that survives its Retry-After, or a captcha wall.
    """

    def __init__(self, url: str, reason: str, status_code: int = 0):
        self.url = url
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"blocked at {url}: {reason}")


@dataclass
class PoliteResponse:
    """Outcome of one polite request.

    Deliberately not an ``httpx.Response``: the shared retry helper inspects
    ``httpx.Response`` objects and would retry status codes we handle here.
    """

    url: str
    status_code: int
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header into seconds.

    Accepts both forms from RFC 9110: delay-seconds and an HTTP-date.
    Returns ``None`` when the header is absent or unparseable.
    """
    if not value:
        return None

    raw = value.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass

    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone

        when = parsedate_to_datetime(raw)
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def looks_like_captcha(body: str) -> bool:
    """True when the response body is an anti-bot challenge, not content."""
    if not body:
        return False
    head = body[:_CAPTCHA_SCAN_CHARS].lower()
    return any(marker in head for marker in CAPTCHA_MARKERS)


class PoliteFetcher:
    """Rate-limited, self-identifying, non-evasive HTTP fetcher."""

    def __init__(
        self,
        user_agent: str,
        rate_limiter: RateLimiter | None = None,
        retry_config: RetryConfig | None = None,
        timeout: float = 30.0,
        source_id: str = "leads",
        max_retry_after_seconds: float = MAX_RETRY_AFTER_SECONDS,
        extra_headers: dict[str, str] | None = None,
    ):
        self.user_agent = user_agent
        self.source_id = source_id
        self._rate_limiter = rate_limiter or RateLimiter(min_delay=3.0, max_delay=5.0)
        self._retry_config = retry_config or RetryConfig()
        self._timeout = timeout
        self._max_retry_after = max_retry_after_seconds
        self._extra_headers = dict(extra_headers or {})
        self._client: httpx.Client | None = None

    # ── identity ──

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        headers.update(self._extra_headers)
        return headers

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            # proxy is intentionally never set: see module docstring.
            self._client = httpx.Client(
                timeout=self._timeout,
                headers=self._headers(),
                follow_redirects=True,
            )
        return self._client

    # ── fetching ──

    def fetch(self, url: str, *, raise_on_block: bool = True, **kwargs: Any) -> PoliteResponse:
        """Fetch a URL politely.

        Waits for the rate limiter, retries transport failures with backoff,
        honours ``Retry-After``, and raises :class:`SourceBlocked` when the
        site signals that we are not welcome.

        Args:
            url: Absolute URL to fetch.
            raise_on_block: When False, a block is returned as a response with
                its status code instead of raising. Used for probing robots.txt.

        Raises:
            SourceBlocked: The site refused us and we will not work around it.
            RetryExhausted: Transport failures outlasted the retry budget.
        """
        response = self._fetch_once(url, **kwargs)

        # A 429 or 503 with Retry-After earns exactly one honoured wait.
        if response.status_code in (429, 503):
            wait = parse_retry_after(response.headers.get("retry-after"))
            if wait is not None and wait <= self._max_retry_after:
                logger.info(
                    f"[{self.source_id}] HTTP {response.status_code} at {url}; "
                    f"honouring Retry-After={wait:.0f}s"
                )
                time.sleep(wait)
                response = self._fetch_once(url, **kwargs)
            elif wait is not None:
                raise SourceBlocked(
                    url,
                    f"Retry-After={wait:.0f}s exceeds the {self._max_retry_after:.0f}s budget",
                    response.status_code,
                )

        blocked_reason = self._block_reason(response)
        if blocked_reason:
            if raise_on_block:
                raise SourceBlocked(url, blocked_reason, response.status_code)
            logger.warning(f"[{self.source_id}] {url}: {blocked_reason}")

        return response

    def _block_reason(self, response: PoliteResponse) -> str:
        """Why this response counts as a block, or '' if it does not."""
        if response.status_code in (401, 403):
            return f"HTTP {response.status_code} — access refused"
        if response.status_code == 429:
            return "HTTP 429 — rate limited beyond Retry-After"
        if response.ok and looks_like_captcha(response.text):
            return "captcha / anti-bot challenge returned instead of content"
        return ""

    def _fetch_once(self, url: str, **kwargs: Any) -> PoliteResponse:
        """One rate-limited request, with backoff on transport errors only."""
        self._rate_limiter.wait()
        client = self._get_client()
        start = time.monotonic()

        def _call() -> PoliteResponse:
            resp = client.get(url, **kwargs)
            return PoliteResponse(
                url=str(resp.url),
                status_code=resp.status_code,
                text=resp.text,
                headers={k.lower(): v for k, v in resp.headers.items()},
            )

        result = with_retry(_call, config=self._retry_config, source_id=self.source_id)()
        result.elapsed_ms = (time.monotonic() - start) * 1000
        return result

    # ── lifecycle ──

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


__all__ = [
    "PoliteFetcher",
    "PoliteResponse",
    "SourceBlocked",
    "RetryExhausted",
    "parse_retry_after",
    "looks_like_captcha",
    "CAPTCHA_MARKERS",
    "MAX_RETRY_AFTER_SECONDS",
]
