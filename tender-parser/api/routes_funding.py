"""API маршруты для программ финансирования МСП (гранты, кредиты, субсидии)."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

# Кэш на 10 минут (данные меняются редко)
_cache: dict[str, tuple[float, Any]] = {}
_TTL = 600


def _cached(key: str) -> Any:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < _TTL:
            return val
    return None


def _set_cache(key: str, val: Any) -> None:
    _cache[key] = (time.time(), val)


def _db():
    try:
        from shared.db import get_db
        return get_db()
    except Exception:
        return None


# Отображаемые названия типов программ
PROGRAM_TYPE_LABELS = {
    "grant": "Грант",
    "loan": "Льготный кредит",
    "microloan": "Микрозайм",
    "subsidy": "Субсидия",
    "guarantee": "Поручительство",
    "compensation": "Компенсация затрат",
    "leasing": "Льготный лизинг",
}

# Отображаемые названия платформ
PLATFORM_LABELS = {
    "corpmsp": "Корпорация МСП",
    "mybusiness": "Мой Бизнес",
    "frprf": "Фонд развития промышленности",
    "mspbank": "МСП Банк",
    "regional": "Региональные программы",
}


def _enrich(row: dict) -> dict:
    """Добавляет человекочитаемые метки к программе."""
    row["program_type_label"] = PROGRAM_TYPE_LABELS.get(
        row.get("program_type", ""), row.get("program_type", "")
    )
    row["platform_label"] = PLATFORM_LABELS.get(
        row.get("source_platform", ""), row.get("source_platform", "")
    )
    return row


@router.get("/funding")
def list_funding(
    q: str | None = Query(None, description="Поиск по названию/описанию"),
    region: str | None = Query(None, description="Регион"),
    program_type: str | None = Query(None, description="Тип: grant, loan, subsidy, guarantee, microloan"),
    industry: str | None = Query(None, description="Отрасль"),
    amount_max: float | None = Query(None, description="Максимальная сумма, руб"),
    status: str = Query("active", description="Статус: active, closed, all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
) -> dict[str, Any]:
    """Список программ финансирования с фильтрами."""
    cli = _db()
    if not cli:
        raise HTTPException(503, "Database not configured")

    qb = cli.table("funding_programs").select("*", count="exact")

    if status != "all":
        qb = qb.eq("status", status)
    if q:
        qb = qb.ilike("program_name", f"%{q}%")
    if program_type:
        qb = qb.eq("program_type", program_type)
    if amount_max is not None:
        # Программы с нижней планкой не выше amount_max
        qb = qb.lte("amount_min", amount_max)
    if region:
        import re
        safe_region = re.sub(r'[,.()\'"\[\]{}]', '', region)
        qb = qb.or_(f"regions.cs.{{{safe_region}}},regions.eq.{{}}")

    start = (page - 1) * page_size
    try:
        res = (
            qb.order("created_at", desc=True)
            .range(start, start + page_size - 1)
            .execute()
        )
    except Exception as e:
        logger.exception("list_funding DB error")
        raise HTTPException(502, "Database query failed") from e
    total = getattr(res, "count", None) or len(res.data or [])
    items = [_enrich(r) for r in (res.data or [])]

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "program_type_labels": PROGRAM_TYPE_LABELS,
        "platform_labels": PLATFORM_LABELS,
    }


@router.get("/funding/meta")
def funding_meta() -> dict[str, Any]:
    """Метаданные: типы программ, платформы, счётчики."""
    cached = _cached("funding_meta")
    if cached:
        return cached

    cli = _db()
    if not cli:
        raise HTTPException(503, "Database not configured")

    try:
        res = cli.table("funding_programs").select("program_type, source_platform, status").execute()
    except Exception as e:
        logger.exception("funding_meta DB error")
        raise HTTPException(502, "Database query failed") from e
    rows = res.data or []

    by_type: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    total_active = 0

    for r in rows:
        pt = r.get("program_type", "other")
        pp = r.get("source_platform", "other")
        st = r.get("status", "")
        by_type[pt] = by_type.get(pt, 0) + 1
        by_platform[pp] = by_platform.get(pp, 0) + 1
        if st == "active":
            total_active += 1

    result = {
        "total": len(rows),
        "total_active": total_active,
        "by_type": by_type,
        "by_platform": by_platform,
        "program_type_labels": PROGRAM_TYPE_LABELS,
        "platform_labels": PLATFORM_LABELS,
    }
    _set_cache("funding_meta", result)
    return result


@router.get("/funding/{program_id}")
def get_funding_program(program_id: str) -> dict[str, Any]:
    """Детали программы финансирования по ID."""
    cli = _db()
    if not cli:
        raise HTTPException(503, "Database not configured")

    try:
        res = (
            cli.table("funding_programs")
            .select("*")
            .eq("id", program_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.exception("get_funding_program DB error")
        raise HTTPException(502, "Database query failed") from e
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Program not found")
    return _enrich(rows[0])
