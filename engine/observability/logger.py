"""Structured logging with correlation IDs and crawl context."""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_crawl_source: ContextVar[str] = ContextVar("crawl_source", default="")


def new_correlation_id() -> str:
    cid = uuid.uuid4().hex[:12]
    _correlation_id.set(cid)
    return cid


def set_crawl_source(source_id: str) -> None:
    _crawl_source.set(source_id)


class StructuredFormatter(logging.Formatter):
    """Formatter that includes correlation_id and source in every log line."""

    def format(self, record: logging.LogRecord) -> str:
        record.correlation_id = _correlation_id.get("")
        record.crawl_source = _crawl_source.get("")
        return super().format(record)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the engine."""
    fmt = (
        "%(asctime)s [%(levelname)s] "
        "[cid=%(correlation_id)s] "
        "[src=%(crawl_source)s] "
        "%(name)s: %(message)s"
    )
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter(fmt))

    root = logging.getLogger("engine")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a logger scoped under engine namespace."""
    return logging.getLogger(f"engine.{name}")


class CrawlLogger:
    """Context-aware logger for a single crawl job."""

    def __init__(self, source_id: str, job_id: str | None = None):
        self.source_id = source_id
        self.job_id = job_id or uuid.uuid4().hex[:8]
        self._log = get_logger(f"crawl.{source_id}")
        set_crawl_source(source_id)

    def _extra(self, **kwargs: Any) -> dict[str, Any]:
        return {"source": self.source_id, "job_id": self.job_id, **kwargs}

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log.info(f"[job={self.job_id}] {msg}", extra=self._extra(**kwargs))

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log.warning(f"[job={self.job_id}] {msg}", extra=self._extra(**kwargs))

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log.error(f"[job={self.job_id}] {msg}", extra=self._extra(**kwargs))

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log.debug(f"[job={self.job_id}] {msg}", extra=self._extra(**kwargs))

    def fetch_ok(self, url: str, elapsed_ms: float) -> None:
        self.debug(f"FETCH OK {url} ({elapsed_ms:.0f}ms)")

    def fetch_fail(self, url: str, error: str) -> None:
        self.warning(f"FETCH FAIL {url}: {error}")

    def parse_ok(self, count: int, url: str) -> None:
        self.info(f"PARSED {count} records from {url}")

    def parse_fail(self, url: str, error: str) -> None:
        self.error(f"PARSE FAIL {url}: {error}")

    def pipeline_result(self, inserted: int, updated: int, skipped: int, errors: int) -> None:
        self.info(
            f"RESULT inserted={inserted} updated={updated} "
            f"skipped={skipped} errors={errors}"
        )
