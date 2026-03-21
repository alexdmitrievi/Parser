"""REST API: тендеры, статистика, ниши (роутер FastAPI)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()


def _client():
    from shared.config import supabase_key, supabase_url
    from supabase import create_client

    url, key = supabase_url(), supabase_key()
    if not url or not key:
        return None
    return create_client(url, key)


@router.get("/tenders")
def list_tenders(
    q: str | None = Query(None, description="Поиск по названию"),
    niche: str | None = None,
    region: str | None = None,
    law: str | None = None,
    status: str | None = Query("active"),
    nmck_min: float | None = None,
    nmck_max: float | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("deadline"),
) -> dict[str, Any]:
    if sort not in ("deadline", "nmck", "created_at"):
        raise HTTPException(400, "Invalid sort")
    cli = _client()
    if not cli:
        raise HTTPException(503, "Database not configured")
    qb = cli.table("tenders").select("*", count="exact")
    if status:
        qb = qb.eq("status", status)
    if q:
        qb = qb.ilike("title", f"%{q}%")
    if region:
        qb = qb.ilike("customer_region", f"%{region}%")
    if law:
        qb = qb.eq("law_type", law)
    if niche:
        qb = qb.contains("niche_tags", [niche])
    if nmck_min is not None:
        qb = qb.gte("nmck", nmck_min)
    if nmck_max is not None:
        qb = qb.lte("nmck", nmck_max)
    order_col = "submission_deadline"
    if sort == "nmck":
        order_col = "nmck"
    elif sort == "created_at":
        order_col = "created_at"
    start = (page - 1) * page_size
    res = (
        qb.order(order_col, desc=True)
        .range(start, start + page_size - 1)
        .execute()
    )
    total = getattr(res, "count", None) or len(res.data or [])
    return {
        "items": res.data or [],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/tenders/{tender_id}")
def get_tender(tender_id: str) -> dict[str, Any]:
    cli = _client()
    if not cli:
        raise HTTPException(503, "Database not configured")
    res = cli.table("tenders").select("*").eq("id", tender_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]


@router.get("/stats")
def stats() -> dict[str, Any]:
    cli = _client()
    if not cli:
        raise HTTPException(503, "Database not configured")
    res = cli.table("tenders").select("niche_tags, customer_region, created_at, nmck").execute()
    rows = res.data or []
    by_niche: dict[str, int] = {}
    by_region: dict[str, int] = {}
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent = 0
    for r in rows:
        for t in r.get("niche_tags") or []:
            by_niche[t] = by_niche.get(t, 0) + 1
        reg = r.get("customer_region") or "unknown"
        by_region[reg] = by_region.get(reg, 0) + 1
        ca = r.get("created_at")
        if isinstance(ca, str):
            try:
                dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                if dt >= week_ago:
                    recent += 1
            except ValueError:
                pass
    return {
        "total": len(rows),
        "by_niche": by_niche,
        "by_region": by_region,
        "created_last_7_days": recent,
    }


@router.get("/niches")
def niches() -> dict[str, Any]:
    cli = _client()
    if not cli:
        raise HTTPException(503, "Database not configured")
    res = cli.table("tenders").select("niche_tags").execute()
    rows = res.data or []
    counts: dict[str, int] = {}
    for r in rows:
        for t in r.get("niche_tags") or []:
            counts[t] = counts.get(t, 0) + 1
    return {"niches": [{"name": k, "count": v} for k, v in sorted(counts.items())]}
