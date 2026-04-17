"""Веб-подписки на тендеры (email в name, синтетический telegram_user_id). Без изменений схемы БД."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web-subscribe"])


def _client():
    try:
        from shared.db import get_db
        return get_db()
    except Exception:
        return None


def _normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def synthetic_telegram_user_id(email: str) -> int:
    """Стабильный положительный int64 из SHA-256 (первые 8 байт)."""
    h = hashlib.sha256(email.encode("utf-8")).digest()
    n = int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF
    return n if n != 0 else 1


def _parse_keywords(text: str | None) -> list[str]:
    if not text or not str(text).strip():
        return []
    parts = re.split(r"[\n,;]+", str(text))
    return [p.strip() for p in parts if p.strip()]


class SubscriptionCreateBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    keywords: str | None = None
    region: str | None = None
    niche: str | None = Field(
        None,
        description="furniture | construction | custom",
    )
    min_nmck: float | None = None
    max_nmck: float | None = None
    law_type: str | None = None


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/subscriptions/create")
def create_subscription(body: SubscriptionCreateBody) -> dict[str, Any]:
    email = _normalize_email(body.email)
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(400, "Некорректный email")

    niche = (body.niche or "").strip().lower() or None
    kw_list = _parse_keywords(body.keywords)
    if niche == "custom" and not kw_list:
        raise HTTPException(400, "Для ниши «свои ключевые слова» укажите ключевые слова")

    if niche and niche != "custom":
        niche_tags = [niche]
    else:
        niche_tags = []

    region = (body.region or "").strip()
    regions = [region] if region else []

    law = (body.law_type or "").strip()
    law_types = [law] if law else []

    cli = _client()
    if not cli:
        raise HTTPException(503, "База данных недоступна")

    row = {
        "telegram_user_id": synthetic_telegram_user_id(email),
        "name": email,
        "keywords": kw_list,
        "regions": regions,
        "okpd2_prefixes": [],
        "min_nmck": body.min_nmck,
        "max_nmck": body.max_nmck,
        "law_types": law_types,
        "niche_tags": niche_tags,
    }

    try:
        res = cli.table("subscriptions").insert(row).execute()
        data = getattr(res, "data", None) or []
        created = data[0] if data else {}
        return {"ok": True, "message": "Подписка активна", "subscription": created}
    except Exception as e:
        logger.exception("create_subscription: %s", e)
        raise HTTPException(500, "Ошибка сохранения подписки") from e


@router.get("/subscriptions/list")
def list_subscriptions(
    email: str = Query(..., min_length=3, description="Email пользователя"),
) -> dict[str, Any]:
    em = _normalize_email(email)
    if not _EMAIL_RE.match(em):
        raise HTTPException(400, "Некорректный email")

    cli = _client()
    if not cli:
        raise HTTPException(503, "База данных недоступна")

    try:
        res = (
            cli.table("subscriptions")
            .select("*")
            .eq("name", em)
            .order("created_at", desc=True)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return {"ok": True, "items": rows, "count": len(rows)}
    except Exception as e:
        logger.exception("list_subscriptions: %s", e)
        raise HTTPException(500, "Ошибка загрузки списка") from e


@router.delete("/subscriptions/{subscription_id}")
def delete_subscription(
    subscription_id: str,
    email: str = Query(..., min_length=3, description="Email для проверки владельца"),
) -> dict[str, Any]:
    em = _normalize_email(email)
    if not _EMAIL_RE.match(em):
        raise HTTPException(400, "Некорректный email")

    cli = _client()
    if not cli:
        raise HTTPException(503, "База данных недоступна")

    try:
        check = (
            cli.table("subscriptions")
            .select("id")
            .eq("id", subscription_id)
            .eq("name", em)
            .limit(1)
            .execute()
        )
        rows = getattr(check, "data", None) or []
        if not rows:
            raise HTTPException(404, "Подписка не найдена или email не совпадает")

        cli.table("subscriptions").delete().eq("id", subscription_id).eq("name", em).execute()
        return {"ok": True, "message": "Подписка удалена"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_subscription: %s", e)
        raise HTTPException(500, "Ошибка удаления") from e
