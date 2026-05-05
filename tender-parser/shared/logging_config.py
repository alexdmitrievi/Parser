"""Structured JSON logging configuration — opt-in via LOG_FORMAT=json env var."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Emit log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["error"] = str(record.exc_info[1])
        if hasattr(record, "extra") and record.extra:
            payload.update(getattr(record, "extra", {}))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Apply JSON logging if LOG_FORMAT=json, otherwise plain text."""
    if os.environ.get("LOG_FORMAT", "").lower() != "json":
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
