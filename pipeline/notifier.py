"""Матчинг новых тендеров с подписками и отправка уведомлений в Telegram."""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from shared.config import get_config
from shared.db import (
    get_new_tenders_since,
    get_subscriptions,
    check_notification_sent,
    log_notification,
)
from bot.messages import format_tender_card

logger = logging.getLogger(__name__)


def _matches_subscription(tender: dict, sub: dict) -> bool:
    """Проверить, подходит ли тендер под подписку."""

    # Проверка по niche_tags
    sub_niches = sub.get("niche_tags") or []
    tender_niches = tender.get("niche_tags") or []
    if sub_niches and not set(sub_niches) & set(tender_niches):
        return False

    # Проверка по ключевым словам
    sub_keywords = sub.get("keywords") or []
    if sub_keywords:
        text = f"{tender.get('title', '')} {tender.get('description', '')}".lower()
        if not any(kw.lower() in text for kw in sub_keywords):
            return False

    # Проверка по регионам
    sub_regions = sub.get("regions") or []
    if sub_regions:
        tender_region = tender.get("customer_region", "")
        if tender_region and not any(r.lower() in tender_region.lower() for r in sub_regions):
            return False

    # Проверка по НМЦК
    tender_nmck = tender.get("nmck")
    if tender_nmck is not None:
        min_nmck = sub.get("min_nmck")
        max_nmck = sub.get("max_nmck")
        if min_nmck is not None and tender_nmck < min_nmck:
            return False
        if max_nmck is not None and tender_nmck > max_nmck:
            return False

    # Проверка по ОКПД2 префиксам
    sub_okpd2 = sub.get("okpd2_prefixes") or []
    tender_okpd2 = tender.get("okpd2_codes") or []
    if sub_okpd2 and tender_okpd2:
        matched = any(
            code.startswith(prefix)
            for code in tender_okpd2
            for prefix in sub_okpd2
        )
        if not matched:
            return False

    # Проверка по типу закона
    sub_laws = sub.get("law_types") or []
    if sub_laws and tender.get("law_type") not in sub_laws:
        return False

    return True


def send_telegram_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Отправить сообщение через Telegram Bot API."""
    cfg = get_config()
    token = cfg["telegram_bot_token"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return True
            else:
                logger.warning(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def _max_per_subscription() -> int:
    """Потолок уведомлений на одну подписку за прогон.

    Без него после долгой паузы в парсинге первый же прогон заливает базу
    бэклогом, и подписчик получает сотни сообщений подряд — это и спам, и
    почти гарантированный лимит Telegram. Ноль отключает ограничение.
    """
    return _safe_int(os.environ.get("MAX_NOTIFICATIONS_PER_SUBSCRIPTION", ""), 10)


def _safe_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def run_notifications(since_minutes: int = 65) -> dict:
    """Основной цикл рассылки уведомлений.

    1. Получить новые тендеры за последний час
    2. Для каждой активной подписки: матчинг
    3. Отправить уведомления, залогировать

    На одну подписку за прогон уходит не больше
    MAX_NOTIFICATIONS_PER_SUBSCRIPTION сообщений (по умолчанию 10);
    остаток отмечается в логе и достанется следующему прогону.

    Returns:
        Статистика: {tenders_checked, subscriptions_checked, notifications_sent,
        notifications_capped}
    """
    stats = {
        "tenders_checked": 0,
        "subscriptions_checked": 0,
        "notifications_sent": 0,
        "notifications_capped": 0,
    }
    max_per_sub = _max_per_subscription()

    # Получить новые тендеры
    new_tenders = get_new_tenders_since(since_minutes)
    stats["tenders_checked"] = len(new_tenders)

    if not new_tenders:
        logger.info("No new tenders found")
        return stats

    logger.info(f"Found {len(new_tenders)} new tenders")

    # Получить все активные подписки
    subscriptions = get_subscriptions()
    stats["subscriptions_checked"] = len(subscriptions)

    if not subscriptions:
        logger.info("No active subscriptions")
        return stats

    logger.info(f"Checking {len(subscriptions)} subscriptions")

    # Матчинг
    for sub in subscriptions:
        sub_id = sub["id"]
        user_id = sub["telegram_user_id"]
        sub_name = sub.get("name", "Без имени")
        sent_for_sub = 0

        for index, tender in enumerate(new_tenders):
            if max_per_sub and sent_for_sub >= max_per_sub:
                # Верхняя оценка: сколько тендеров осталось непросмотренными.
                # Точное число совпадений считать не станем — это по запросу
                # в БД на каждый тендер, а на бэклоге их тысячи.
                deferred = len(new_tenders) - index
                stats["notifications_capped"] += deferred
                logger.warning(
                    f"  Sub '{sub_name}' hit the per-run cap ({max_per_sub}); "
                    f"up to {deferred} tenders deferred to the next run"
                )
                break

            tender_id = tender["id"]

            # Уже отправляли?
            if check_notification_sent(sub_id, tender_id):
                continue

            # Подходит под подписку?
            if not _matches_subscription(tender, sub):
                continue

            # Отправить
            message = f"🔔 <b>Новый тендер по подписке «{sub_name}»:</b>\n\n"
            message += format_tender_card(tender)

            if send_telegram_message(user_id, message):
                log_notification(sub_id, tender_id)
                stats["notifications_sent"] += 1
                sent_for_sub += 1
                logger.info(f"  Sent notification: sub={sub_name}, tender={tender_id}")

    logger.info(f"Notifications sent: {stats['notifications_sent']}")
    return stats
