"""Главный обработчик Telegram webhook.

Чистый Telegram Bot API через httpx (без aiogram — для serverless).
Роутинг команд и callback_query.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.config import get_config
from shared.db import register_user, search_tenders, get_subscriptions, count_tenders
from shared.models import SearchFilters, SubscriptionCreate
from bot.messages import (
    WELCOME_MESSAGE, HELP_MESSAGE,
    format_tender_list, format_tender_card,
)
from bot.keyboards import (
    MAIN_MENU, NICHE_KEYBOARD, NMCK_KEYBOARD,
    region_keyboard, pagination_keyboard, subscription_list_keyboard,
    confirm_subscription_keyboard,
)

logger = logging.getLogger(__name__)

# Временное хранилище состояния пользователя (в Vercel — per-request, поэтому
# для wizard используем callback_data с закодированным состоянием)
# В production: Upstash Redis


def _tg_api(method: str, payload: dict) -> dict:
    """Вызвать метод Telegram Bot API."""
    cfg = get_config()
    token = cfg["telegram_bot_token"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload)
            return resp.json()
    except Exception as e:
        logger.error(f"Telegram API error: {e}")
        return {}


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _tg_api("sendMessage", payload)


def edit_message(chat_id: int, message_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _tg_api("editMessageText", payload)


def answer_callback(callback_query_id: str, text: str = "") -> dict:
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return _tg_api("answerCallbackQuery", payload)


# ──────── Обработчики команд ────────


def handle_start(chat_id: int, user: dict) -> None:
    register_user(
        telegram_user_id=chat_id,
        username=user.get("username", ""),
        first_name=user.get("first_name", ""),
    )
    send_message(chat_id, WELCOME_MESSAGE, MAIN_MENU)


def handle_help(chat_id: int) -> None:
    send_message(chat_id, HELP_MESSAGE, MAIN_MENU)


def handle_search_start(chat_id: int, message_id: int | None = None) -> None:
    text = "🔍 <b>Поиск тендеров</b>\n\nВыберите категорию:"
    if message_id:
        edit_message(chat_id, message_id, text, NICHE_KEYBOARD)
    else:
        send_message(chat_id, text, NICHE_KEYBOARD)


def handle_niche_select(chat_id: int, message_id: int, niche: str) -> None:
    if niche == "custom":
        text = "🔎 Введите поисковый запрос (ключевые слова):"
        edit_message(chat_id, message_id, text)
        # Следующее текстовое сообщение будет обработано как поисковый запрос
        return

    text = f"📍 Выберите регион для ниши <b>{'🛋 Мебель' if niche == 'furniture' else '🏗 Подряды'}</b>:"
    edit_message(chat_id, message_id, text, region_keyboard())


def handle_region_select(chat_id: int, message_id: int, region: str, niche: str = "") -> None:
    text = "💰 Выберите диапазон НМЦК:"
    edit_message(chat_id, message_id, text, NMCK_KEYBOARD)


def handle_search_execute(chat_id: int, message_id: int | None, filters: SearchFilters) -> None:
    """Выполнить поиск и отправить результаты."""
    tenders = search_tenders(filters)
    total = count_tenders(filters)
    total_pages = max(1, (total + filters.per_page - 1) // filters.per_page)

    text = format_tender_list(tenders, filters.page, total, filters.per_page)
    kb = pagination_keyboard(filters.page, total_pages) if total > 0 else MAIN_MENU

    if message_id:
        edit_message(chat_id, message_id, text, kb)
    else:
        send_message(chat_id, text, kb)


def handle_hot(chat_id: int, message_id: int | None = None) -> None:
    """Горячие тендеры — дедлайн менее 3 дней."""
    from datetime import datetime, timedelta, timezone
    from shared.db import get_db

    db = get_db()
    cutoff = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

    try:
        result = (
            db.table("tenders")
            .select("*")
            .eq("status", "active")
            .lte("submission_deadline", cutoff)
            .gte("submission_deadline", datetime.now(timezone.utc).isoformat())
            .order("submission_deadline", desc=False)
            .limit(10)
            .execute()
        )
        tenders = result.data or []
    except Exception as e:
        logger.error(f"Error fetching hot tenders: {e}")
        tenders = []

    if tenders:
        text = f"🔥 <b>Горячие тендеры</b> (дедлайн &lt; 3 дней):\n\n"
        cards = [format_tender_card(t) for t in tenders[:5]]
        text += "\n\n━━━━━━━━━━━━━━━\n\n".join(cards)
    else:
        text = "🔥 Горячих тендеров сейчас нет. Попробуйте позже."

    if message_id:
        edit_message(chat_id, message_id, text, MAIN_MENU)
    else:
        send_message(chat_id, text, MAIN_MENU)


def handle_mysubs(chat_id: int, message_id: int | None = None) -> None:
    subs = get_subscriptions(telegram_user_id=chat_id)

    if subs:
        text = f"📋 <b>Ваши подписки ({len(subs)}):</b>"
        kb = subscription_list_keyboard(subs)
    else:
        text = "📋 У вас пока нет подписок.\n\nСоздайте первую — и бот будет присылать подходящие тендеры автоматически."
        from bot.keyboards import inline_keyboard, inline_button
        kb = inline_keyboard([
            [inline_button("➕ Создать подписку", "subscribe:start")],
            [inline_button("« Главное меню", "main_menu")],
        ])

    if message_id:
        edit_message(chat_id, message_id, text, kb)
    else:
        send_message(chat_id, text, kb)


# ──────── Callback query роутер ────────


def handle_callback(callback_query: dict) -> None:
    """Обработать callback_query от inline-кнопок."""
    cb_id = callback_query["id"]
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    if not chat_id:
        answer_callback(cb_id)
        return

    answer_callback(cb_id)

    # Роутинг
    if data == "main_menu":
        edit_message(chat_id, message_id, WELCOME_MESSAGE, MAIN_MENU)

    elif data == "search:start":
        handle_search_start(chat_id, message_id)

    elif data.startswith("niche:"):
        niche = data.split(":")[1]
        handle_niche_select(chat_id, message_id, niche)

    elif data.startswith("region:"):
        region = data.split(":")[1]
        handle_region_select(chat_id, message_id, region)

    elif data.startswith("nmck:"):
        nmck_str = data.split(":")[1]
        filters = SearchFilters(status="active")

        if nmck_str != "any":
            parts = nmck_str.split("-")
            if len(parts) == 2:
                min_v, max_v = int(parts[0]), int(parts[1])
                if min_v > 0:
                    filters.min_nmck = float(min_v)
                if max_v > 0:
                    filters.max_nmck = float(max_v)

        handle_search_execute(chat_id, message_id, filters)

    elif data.startswith("page:"):
        page = int(data.split(":")[1])
        filters = SearchFilters(status="active", page=page)
        handle_search_execute(chat_id, message_id, filters)

    elif data == "hot":
        handle_hot(chat_id, message_id)

    elif data == "mysubs":
        handle_mysubs(chat_id, message_id)

    elif data == "help":
        edit_message(chat_id, message_id, HELP_MESSAGE, MAIN_MENU)

    elif data.startswith("sub_delete:"):
        sub_id = data.split(":")[1]
        from shared.db import delete_subscription
        delete_subscription(sub_id, chat_id)
        answer_callback(cb_id, "✅ Подписка удалена")
        handle_mysubs(chat_id, message_id)

    elif data == "subscribe:start" or data == "sub:from_search":
        text = "📋 <b>Создание подписки</b>\n\nВыберите нишу:"
        edit_message(chat_id, message_id, text, NICHE_KEYBOARD)

    elif data == "noop":
        pass


# ──────── Главный роутер ────────


def handle_update(update: dict) -> None:
    """Обработать входящий Update от Telegram."""

    # Callback query (нажатие на inline-кнопку)
    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return

    # Текстовое сообщение
    message = update.get("message", {})
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    user = message.get("from", {})

    if not chat_id or not text:
        return

    # Команды
    if text == "/start":
        handle_start(chat_id, user)
    elif text == "/help":
        handle_help(chat_id)
    elif text == "/search":
        handle_search_start(chat_id)
    elif text == "/hot":
        handle_hot(chat_id)
    elif text == "/mysubs":
        handle_mysubs(chat_id)
    elif text == "/subscribe":
        send_message(chat_id, "📋 <b>Создание подписки</b>\n\nВыберите нишу:", NICHE_KEYBOARD)
    else:
        # Текстовый поиск (после "Свой запрос")
        filters = SearchFilters(query=text, status="active")
        handle_search_execute(chat_id, None, filters)
