"""Даты в UTC для нормализации."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser


def to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime_ru(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    try:
        dt = date_parser.parse(str(value), dayfirst=True)
        return to_utc(dt)
    except (ValueError, TypeError, OverflowError):
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def jsonable_dt(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
