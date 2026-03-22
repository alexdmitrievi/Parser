"""Форматирование сообщений бота."""

from __future__ import annotations

from typing import Any


def _fmt_money(n: float | int | None) -> str:
    if n is None:
        return "—"
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        return str(n)
    s = f"{v:,}".replace(",", " ")
    return f"{s} ₽"


def format_tender_card(t: dict[str, Any]) -> str:
    """Краткая карточка тендера для Telegram."""
    title = str(t.get("title") or "Без названия")
    nmck = _fmt_money(t.get("nmck"))
    law = str(t.get("law_type") or "—")
    customer = str(t.get("customer_name") or "—")
    region = str(t.get("customer_region") or "—")
    deadline = str(t.get("submission_deadline") or "—")
    url = str(t.get("original_url") or "").strip()
    tags = t.get("niche_tags") or []
    tags_s = ", ".join(tags) if tags else "—"
    lines = [
        f"📌 {title}",
        f"💰 НМЦК: {nmck} · {law}",
        f"🏢 {customer}",
        f"📍 {region}",
        f"📅 Дедлайн: {deadline}",
        f"🏷 {tags_s}",
    ]
    if url:
        lines.append(f"🔗 {url}")
    return "\n".join(lines)
