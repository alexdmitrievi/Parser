"""Обновление статусов тендеров: дедлайн и HTML ЕИС."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

from shared.time_utils import now_utc

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def mark_expired_by_deadline(rows: list[dict]) -> list[dict]:
    """Пометить expired, если active и дедлайн в прошлом."""
    now = now_utc()
    updates: list[dict] = []
    for r in rows:
        if str(r.get("status")) != "active":
            continue
        d = r.get("submission_deadline")
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d.replace("Z", "+00:00"))
            except ValueError:
                d = None
        if isinstance(d, datetime):
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            if d < now:
                updates.append({"id": r["id"], "status": "expired"})
    return updates


def fetch_eis_status(registry_number: str) -> str | None:
    """
    По HTML карточки закупки на ЕИС вернуть completed / cancelled или None.
    """
    if not registry_number:
        return None
    url = (
        "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html"
        f"?regNumber={registry_number}"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=45)
        r.raise_for_status()
        html = r.text.lower()
    except requests.RequestException as e:
        logger.debug("eis status fetch failed %s: %s", registry_number, e)
        return None

    if "закупка отменена" in html or "отменена" in html and "закупк" in html:
        return "cancelled"
    if "работа комиссии" in html or "определение поставщика завершено" in html:
        return "completed"
    return None


def infer_status_from_html(html: str) -> str | None:
    h = html.lower()
    if re.search(r"закупк[аи]\s+отменен", h):
        return "cancelled"
    if "работа комиссии" in h or "определение поставщика завершено" in h:
        return "completed"
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
