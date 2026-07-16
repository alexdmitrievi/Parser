"""Карточки закупок и их отправка владельцу.

Формат карточки (ровно эти поля, по ТЗ):
НМЦК · регион · способ закупки · дедлайн подачи · размер обеспечения · ссылка.
Наименование закупки идёт заголовком. Кнопок действий нет.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from monitor.business_filter import BusinessFilter
from monitor.telegram_client import send_message

logger = logging.getLogger("monitor.notifier")


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{int(round(v)):,}".replace(",", " ")
    return f"{s} ₽"


_MSK = timezone(timedelta(hours=3))

# Канонические коды способов закупки (engine/normalizers/purchase_method.py)
# → человекочитаемые названия для карточки
_METHOD_DISPLAY = {
    "auction": "Электронный аукцион",
    "contest": "Открытый конкурс",
    "quotation": "Запрос котировок",
    "proposal": "Запрос предложений",
    "single_source": "Закупка у единственного поставщика",
    "limited_contest": "Конкурс с ограниченным участием",
    "two_stage_contest": "Двухэтапный конкурс",
    "other": "Иное",
}


def _fmt_method(value: Any) -> str:
    if not value:
        return "—"
    return _METHOD_DISPLAY.get(str(value), str(value))


def _fmt_deadline(value: Any) -> str:
    """Дедлайн в московском времени (в датах выгрузок ЕИС — смещение +03:00)."""
    if value is None:
        return "—"
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if value.tzinfo is not None:
        return value.astimezone(_MSK).strftime("%d.%m.%Y %H:%M МСК")
    return value.strftime("%d.%m.%Y %H:%M")


def _fmt_guarantee(tender: dict[str, Any]) -> str:
    app = tender.get("application_guarantee")
    con = tender.get("contract_guarantee")
    if app is None and con is None:
        return "—"
    parts = []
    if app is not None:
        parts.append(f"заявка {_fmt_money(app)}")
    if con is not None:
        parts.append(f"контракт {_fmt_money(con)}")
    return " · ".join(parts)


def format_card(tender: dict[str, Any]) -> str:
    """Карточка уведомления для Telegram (HTML)."""
    title = html.escape(str(tender.get("title") or "Без названия"))
    law = str(tender.get("law_type") or "").upper().replace("-FZ", "-ФЗ")
    url = str(tender.get("original_url") or "").strip()

    lines = [
        f"🔔 <b>{title}</b>",
        f"💰 НМЦК: {_fmt_money(tender.get('nmck'))}" + (f" · {law}" if law else ""),
        f"📍 {tender.get('customer_region') or '—'}",
        f"⚙️ Способ: {_fmt_method(tender.get('purchase_method'))}",
        f"⏰ Дедлайн подачи: {_fmt_deadline(tender.get('submission_deadline'))}",
        f"🛡 Обеспечение: {_fmt_guarantee(tender)}",
    ]
    if url:
        lines.append(f'🔗 <a href="{html.escape(url)}">Карточка закупки</a>')
    return "\n".join(lines)


def notify_new_tenders(repo, business_filter: BusinessFilter) -> dict[str, int]:
    """Отправить карточки по новым закупкам, прошедшим фильтры.

    Дубликаты исключены таблицей notified_tenders (PK по номеру извещения).
    """
    stats = {"checked": 0, "matched": 0, "sent": 0}
    candidates = repo.fetch_unnotified_tenders(since_hours=48)
    stats["checked"] = len(candidates)

    for tender in candidates:
        if not business_filter.matches(tender):
            continue
        stats["matched"] += 1
        if send_message(format_card(tender)):
            repo.mark_notified([tender["registry_number"]])
            stats["sent"] += 1
        else:
            logger.error(
                f"Failed to send card for {tender.get('registry_number')} — "
                "will retry next cycle"
            )

    logger.info(
        f"Notifier: {stats['checked']} candidates, "
        f"{stats['matched']} matched filters, {stats['sent']} sent"
    )
    return stats
