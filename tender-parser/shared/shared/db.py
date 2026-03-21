"""Supabase / PostgreSQL клиент для тендеров и состояния бота."""

from __future__ import annotations

import logging
import math
from typing import Any

from shared.config import supabase_key, supabase_url
from shared.models import SearchFilters

logger = logging.getLogger(__name__)

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    url, key = supabase_url(), supabase_key()
    if not url or not key:
        logger.warning("Supabase URL/key not configured")
        return None
    from supabase import create_client

    _client = create_client(url, key)
    return _client


def get_db() -> Any:
    """Клиент Supabase (как в smoke-тестах)."""
    cli = _get_client()
    if not cli:
        raise RuntimeError("Supabase is not configured (SUPABASE_URL / SUPABASE_KEY)")
    return cli


def _build_query(cli: Any, filters: SearchFilters):
    qb = cli.table("tenders").select("*", count="exact")
    if filters.status:
        qb = qb.eq("status", filters.status)
    if filters.query:
        qb = qb.ilike("title", f"%{filters.query}%")
    if filters.region:
        qb = qb.ilike("customer_region", f"%{filters.region}%")
    if filters.law:
        qb = qb.eq("law_type", filters.law)
    if filters.niche:
        qb = qb.contains("niche_tags", [filters.niche])
    if filters.min_nmck is not None:
        qb = qb.gte("nmck", filters.min_nmck)
    if filters.max_nmck is not None:
        qb = qb.lte("nmck", filters.max_nmck)
    return qb


def count_tenders(filters: SearchFilters) -> int:
    """Количество строк по фильтрам (для «страница 1/12»)."""
    cli = _get_client()
    if not cli:
        return 0
    try:
        qb = _build_query(cli, filters)
        res = qb.limit(1).execute()
        c = getattr(res, "count", None)
        if c is not None:
            return int(c)
        return len(getattr(res, "data", None) or [])
    except Exception as e:
        logger.exception("count_tenders: %s", e)
        return 0


def search_tenders(filters: SearchFilters) -> list[dict[str, Any]]:
    """Выборка страницы результатов."""
    cli = _get_client()
    if not cli:
        return []
    try:
        qb = _build_query(cli, filters)
        order_col = "submission_deadline"
        page = max(1, filters.page)
        per = max(1, min(50, filters.per_page))
        start = (page - 1) * per
        res = qb.order(order_col, desc=True).range(start, start + per - 1).execute()
        return list(getattr(res, "data", None) or [])
    except Exception as e:
        logger.exception("search_tenders: %s", e)
        return []


def total_pages(filters: SearchFilters) -> int:
    total = count_tenders(filters)
    per = max(1, filters.per_page)
    return max(1, math.ceil(total / per)) if total else 1


def get_user_state(telegram_user_id: int) -> dict[str, Any]:
    cli = _get_client()
    if not cli:
        return {}
    try:
        res = (
            cli.table("bot_state")
            .select("state")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        if not rows:
            return {}
        st = rows[0].get("state")
        return dict(st) if isinstance(st, dict) else {}
    except Exception as e:
        logger.exception("get_user_state: %s", e)
        return {}


def set_user_state(telegram_user_id: int, state: dict[str, Any]) -> None:
    cli = _get_client()
    if not cli:
        return
    try:
        cli.table("bot_state").upsert(
            {"telegram_user_id": telegram_user_id, "state": state},
            on_conflict="telegram_user_id",
        ).execute()
    except Exception as e:
        logger.exception("set_user_state: %s", e)


def clear_user_state(telegram_user_id: int) -> None:
    cli = _get_client()
    if not cli:
        return
    try:
        cli.table("bot_state").delete().eq("telegram_user_id", telegram_user_id).execute()
    except Exception as e:
        logger.exception("clear_user_state: %s", e)


def upsert_tender(row: dict[str, Any]) -> None:
    cli = _get_client()
    if not cli:
        return
    try:
        cli.table("tenders").upsert(row, on_conflict="registry_number").execute()
    except Exception as e:
        logger.exception("upsert_tender: %s", e)


def fetch_tender_by_registry(registry_number: str) -> dict[str, Any] | None:
    cli = _get_client()
    if not cli:
        return None
    try:
        res = (
            cli.table("tenders")
            .select("*")
            .eq("registry_number", registry_number)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return rows[0] if rows else None
    except Exception as e:
        logger.exception("fetch_tender_by_registry: %s", e)
        return None
