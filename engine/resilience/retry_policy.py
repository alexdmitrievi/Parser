"""Retry policy with exponential backoff and error classification."""

from __future__ import annotations

import time
import random
from typing import Callable, TypeVar, Any

import httpx

from engine.types import RetryConfig
from engine.observability.logger import get_logger

logger = get_logger("retry")

T = TypeVar("T")

# Errors that should trigger retry
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    ConnectionError,
    TimeoutError,
    OSError,
)

# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}


class RetryExhausted(Exception):
    """All retry attempts exhausted."""

    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")


def _should_retry_exception(exc: Exception) -> bool:
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return False


def _backoff_delay(attempt: int, config: RetryConfig) -> float:
    """Exponential backoff with jitter."""
    delay = min(config.backoff_base ** attempt, config.backoff_max)
    jitter = random.uniform(0, delay * 0.3)
    return delay + jitter


def with_retry(
    fn: Callable[..., T],
    config: RetryConfig | None = None,
    source_id: str = "",
) -> Callable[..., T]:
    """Wrap a callable with retry logic.

    Usage:
        result = with_retry(lambda: fetcher.get(url), config=retry_config, source_id="eis")()
    """
    if config is None:
        config = RetryConfig()

    def wrapper(*args: Any, **kwargs: Any) -> T:
        last_error: Exception | None = None

        for attempt in range(1, config.max_attempts + 1):
            try:
                result = fn(*args, **kwargs)

                # Check HTTP response status
                if isinstance(result, httpx.Response) and result.status_code in RETRYABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"HTTP {result.status_code}",
                        request=result.request,
                        response=result,
                    )

                return result

            except Exception as e:
                last_error = e

                if not _should_retry_exception(e):
                    raise

                if attempt < config.max_attempts:
                    delay = _backoff_delay(attempt, config)
                    logger.warning(
                        f"[{source_id}] Attempt {attempt}/{config.max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    time.sleep(delay)

        raise RetryExhausted(last_error, config.max_attempts)  # type: ignore[arg-type]

    return wrapper
