"""Новые маршруты поиска тендеров для веб-интерфейса (тот же слой, что и Telegram-бот)."""

from __future__ import annotations

import logging
import math
import traceback
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from bot.messages import format_tender_card
from shared.config import supabase_key, supabase_url
from shared.db import count_tenders, search_tenders as fetch_tenders
from shared.models import SearchFilters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web-search"])


@router.get("/search/tenders")
def search_tenders_web(
    q: str | None = Query(None, description="Ключевые слова (полнотекстовый поиск)"),
    region: str | None = Query(None, description="Регион (точное совпадение)"),
    niche: str | None = Query(None, description="Тег ниши, например furniture"),
    min_nmck: float | None = Query(None),
    max_nmck: float | None = Query(None),
    law_type: str | None = Query(None, description="44-fz, 223-fz, commercial"),
    status: str = Query("active"),
    page: int = Query(1, ge=1),
    per_page: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    """Поиск как в боте: SearchFilters + count_tenders + search_tenders, карточки как format_tender_card."""
    if not supabase_url() or not supabase_key():
        raise HTTPException(
            status_code=503,
            detail="База данных не настроена: задайте SUPABASE_URL и SUPABASE_KEY или SUPABASE_SERVICE_ROLE_KEY",
        )
    filters_dict: dict[str, Any] = {
        "query": (q or "").strip() or None,
        "region": region or None,
        "min_nmck": min_nmck,
        "max_nmck": max_nmck,
        "niche": niche or None,
        "law_type": law_type or None,
        "status": status or "active",
    }
    try:
        fl = SearchFilters.from_state_dict(filters_dict, page=page, per_page=per_page)
        total = count_tenders(fl)
        per = max(1, fl.per_page)
        pages = max(1, math.ceil(total / per)) if total else 1
        safe_page = min(max(1, page), pages)
        fl = fl.model_copy(update={"page": safe_page})
        rows = fetch_tenders(fl)
        cards = [format_tender_card(r) for r in rows]
        return {
            "total": total,
            "page": safe_page,
            "pages": pages,
            "per_page": per,
            "items": rows,
            "cards": cards,
        }
    except Exception as e:
        logger.error(f"search error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, detail=f"Ошибка поиска: {e}")
