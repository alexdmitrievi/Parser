"""Production-grade base scraper: token-bucket rate limiter, circuit breaker, metrics."""

from __future__ import annotations

import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# ─── Пул User-Agent (15 актуальных вариантов) ────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 OPR/111.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 14; Mobile; rv:126.0) Gecko/126.0 Firefox/126.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

_ACCEPT_BY_ENGINE = {
    "firefox": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "safari": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "chrome": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
}


# ─── Метрики скрапера ─────────────────────────────────────────────────────────

@dataclass
class ScraperMetrics:
    """Статистика одного прогона скрапера."""
    requests_total: int = 0
    requests_ok: int = 0
    requests_failed: int = 0
    items_parsed: int = 0
    retries_total: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def success_rate(self) -> float:
        if self.requests_total == 0:
            return 1.0
        return self.requests_ok / self.requests_total

    def summary(self) -> str:
        return (
            f"requests={self.requests_total} ok={self.requests_ok} "
            f"failed={self.requests_failed} retries={self.retries_total} "
            f"items={self.items_parsed} elapsed={self.elapsed:.1f}s "
            f"success_rate={self.success_rate:.0%}"
        )


# ─── Токен-бакет (rate limiting per domain) ──────────────────────────────────

class _TokenBucket:
    """Thread-safe token bucket для одного домена."""

    def __init__(self, rate: float, burst: int = 3) -> None:
        self._rate = rate       # tokens/second
        self._tokens = float(burst)
        self._burst = burst
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Блокируется до получения разрешения на запрос."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            time.sleep(0.05)


_domain_buckets: dict[str, _TokenBucket] = {}
_domain_buckets_lock = threading.Lock()


def _get_bucket(url: str, min_delay: float, max_delay: float) -> _TokenBucket:
    """Получить или создать токен-бакет для домена URL."""
    domain = urlparse(url).netloc or url
    with _domain_buckets_lock:
        if domain not in _domain_buckets:
            avg = (min_delay + max_delay) / 2
            _domain_buckets[domain] = _TokenBucket(rate=1.0 / max(avg, 0.5), burst=2)
        return _domain_buckets[domain]


# ─── Circuit Breaker ──────────────────────────────────────────────────────────

class _CircuitBreaker:
    """Размыкатель: после N ошибок подряд блокирует запросы на RECOVERY_TIMEOUT."""

    THRESHOLD = 5
    RECOVERY_TIMEOUT = 120  # seconds

    def __init__(self) -> None:
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at > self.RECOVERY_TIMEOUT:
                self._opened_at = None
                self._failures = 0
                return False
            return True

    def on_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def on_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.THRESHOLD:
                self._opened_at = time.monotonic()
                logger.warning(f"Circuit breaker OPEN after {self._failures} failures")


# ─── Base Scraper ─────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """Абстрактный производственный скрапер.

    Подклассы обязаны задать:
        platform: str       — идентификатор площадки
        base_url: str       — корневой URL
        min_delay: float    — минимальная задержка между запросами (секунды)
        max_delay: float    — максимальная задержка

    И реализовать:
        parse_tenders(raw_data) -> list[TenderCreate]
        run(**kwargs)           -> list[TenderCreate]
    """

    platform: str = "unknown"
    base_url: str = ""
    min_delay: float = 2.0
    max_delay: float = 6.0
    timeout: float = 30.0
    connect_timeout: float = 10.0
    max_retries: int = 3

    def __init__(self) -> None:
        self._client: Optional[httpx.Client] = None
        self.metrics = ScraperMetrics()
        self._circuit = _CircuitBreaker()

    # ── HTTP client ──────────────────────────────────────────────────────────

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=httpx.Timeout(
                    connect=self.connect_timeout,
                    read=self.timeout,
                    write=10.0,
                    pool=60.0,
                ),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=30,
                ),
                headers=self._build_headers(),
                follow_redirects=True,
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        ua = random.choice(USER_AGENTS)
        if "Firefox" in ua:
            accept = _ACCEPT_BY_ENGINE["firefox"]
        elif "Safari" in ua and "Chrome" not in ua:
            accept = _ACCEPT_BY_ENGINE["safari"]
        else:
            accept = _ACCEPT_BY_ENGINE["chrome"]

        return {
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

    # ── Rate limiting + delay ─────────────────────────────────────────────────

    def _delay(self, url: str = "") -> None:
        """Адаптивная задержка: токен-бакет + случайный джиттер."""
        target = url or self.base_url
        _get_bucket(target, self.min_delay, self.max_delay).acquire()
        jitter = random.uniform(0, (self.max_delay - self.min_delay) * 0.25)
        if jitter > 0.05:
            time.sleep(jitter)

    # ── HTTP methods ──────────────────────────────────────────────────────────

    def fetch(self, url: str, **kwargs) -> httpx.Response:
        """HTTP GET с rate limiting, retry и circuit breaker."""
        if self._circuit.is_open:
            raise RuntimeError(f"[{self.platform}] circuit breaker OPEN — skipping {url}")

        self._delay(url)
        self.metrics.requests_total += 1
        logger.debug(f"[{self.platform}] GET {url}")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.get(url, **kwargs)
                resp.raise_for_status()
                self.metrics.requests_ok += 1
                self._circuit.on_success()
                return resp
            except (httpx.HTTPStatusError, httpx.ConnectError,
                    httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self.metrics.retries_total += 1
                    backoff = min(2 ** attempt + random.uniform(0, 1), 30)
                    logger.warning(
                        f"[{self.platform}] retry {attempt}/{self.max_retries} "
                        f"({type(exc).__name__}) — backoff {backoff:.1f}s"
                    )
                    time.sleep(backoff)
                    # Refresh headers on retry (new User-Agent)
                    if self._client and not self._client.is_closed:
                        self._client.headers.update(self._build_headers())

        self.metrics.requests_failed += 1
        self._circuit.on_failure()
        raise last_exc  # type: ignore[misc]

    def post(self, url: str, **kwargs) -> httpx.Response:
        """HTTP POST с rate limiting, retry и circuit breaker."""
        if self._circuit.is_open:
            raise RuntimeError(f"[{self.platform}] circuit breaker OPEN — skipping POST {url}")

        self._delay(url)
        self.metrics.requests_total += 1
        logger.debug(f"[{self.platform}] POST {url}")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.post(url, **kwargs)
                resp.raise_for_status()
                self.metrics.requests_ok += 1
                self._circuit.on_success()
                return resp
            except (httpx.HTTPStatusError, httpx.ConnectError,
                    httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self.metrics.retries_total += 1
                    backoff = min(2 ** attempt + random.uniform(0, 1), 30)
                    logger.warning(
                        f"[{self.platform}] POST retry {attempt}/{self.max_retries} "
                        f"— backoff {backoff:.1f}s"
                    )
                    time.sleep(backoff)

        self.metrics.requests_failed += 1
        self._circuit.on_failure()
        raise last_exc  # type: ignore[misc]

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def parse_tenders(self, raw_data: Any) -> list[TenderCreate]:
        """Распарсить сырые данные в список тендеров."""
        ...

    @abstractmethod
    def run(self, **kwargs) -> list[TenderCreate]:
        """Запустить полный цикл парсинга. Возвращает список тендеров."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()
        logger.info(f"[{self.platform}] done — {self.metrics.summary()}")

    def __enter__(self) -> "BaseScraper":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
