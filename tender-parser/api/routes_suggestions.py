"""API подсказок для автокомплита: регионы, заказчики, справочники."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from shared.constants import RUSSIAN_REGIONS, PLATFORMS, PURCHASE_METHODS
from shared.db import suggest_regions as db_suggest_regions, suggest_customers as db_suggest_customers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["suggestions"])


@router.get("/suggest/regions")
def suggest_regions(
    q: str = Query("", min_length=0, description="Подстрока для поиска региона"),
) -> dict[str, Any]:
    """Подсказки регионов: сначала из справочника RUSSIAN_REGIONS, потом из БД."""
    q = (q or "").strip().lower()
    if not q or len(q) < 1:
        return {"items": RUSSIAN_REGIONS[:15]}

    # Фильтруем по справочнику (мгновенно, без запросов к БД)
    local = [r for r in RUSSIAN_REGIONS if q in r.lower()][:10]

    # Дополняем из БД если мало результатов
    if len(local) < 5:
        try:
            db_results = db_suggest_regions(q, limit=10)
            seen = {r.lower() for r in local}
            for r in db_results:
                if r.lower() not in seen:
                    local.append(r)
                    seen.add(r.lower())
                    if len(local) >= 10:
                        break
        except Exception as e:
            logger.warning(f"suggest_regions db fallback: {e}")

    return {"items": local}


@router.get("/suggest/customers")
def suggest_customers(
    q: str = Query("", min_length=2, description="Подстрока для поиска заказчика"),
) -> dict[str, Any]:
    """Подсказки заказчиков из БД."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"items": []}
    try:
        results = db_suggest_customers(q, limit=10)
        return {"items": results}
    except Exception as e:
        logger.warning(f"suggest_customers: {e}")
        return {"items": []}


@router.get("/suggest/platforms")
def suggest_platforms() -> dict[str, Any]:
    """Справочник площадок."""
    items = [{"id": k, "name": v["name"]} for k, v in PLATFORMS.items()]
    return {"items": items}


@router.get("/suggest/purchase-methods")
def suggest_purchase_methods() -> dict[str, Any]:
    """Справочник способов закупки."""
    items = [{"id": k, "name": v} for k, v in PURCHASE_METHODS.items()]
    return {"items": items}
