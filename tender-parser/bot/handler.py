"""Обработчики Telegram с сохранением шага wizard в Supabase (bot_state)."""

from __future__ import annotations

import logging
import math
import os
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.messages import format_tender_card
from shared.config import supabase_key, supabase_url
from shared.db import (
    clear_user_state,
    count_tenders,
    get_user_state,
    register_user,
    search_tenders,
    set_user_state,
)
from shared.models import SearchFilters

logger = logging.getLogger(__name__)

MAX_MSG_LEN = 3900


def _state(uid: int) -> dict[str, Any]:
    return get_user_state(uid)


def _save(uid: int, **kwargs: Any) -> None:
    st = _state(uid)
    st.update(kwargs)
    set_user_state(uid, st)


def _reset(uid: int) -> None:
    clear_user_state(uid)


async def process_update(update_dict: dict[str, Any]) -> None:
    """Для Vercel webhook: разбор JSON Update и прогон через то же приложение."""
    application = build_application()
    await application.initialize()
    try:
        update = Update.de_json(update_dict, application.bot)
        await application.process_update(update)
    except Exception:
        logger.exception("process_update failed")
    finally:
        await application.shutdown()


async def handle_search_execute(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    filters: SearchFilters,
) -> None:
    """Реальный поиск в Supabase + пагинация (count для «стр. 1/12»)."""
    total = count_tenders(filters)
    per = max(1, filters.per_page)
    pages = max(1, math.ceil(total / per)) if total else 1
    page = min(max(1, filters.page), pages)
    filters = filters.model_copy(update={"page": page})
    rows = search_tenders(filters)

    header = f"Найдено: {total} · стр. {page}/{pages}\n\n"
    if not rows:
        text = header + "Ничего не найдено. Уточните запрос или проверьте Supabase."
    else:
        parts: list[str] = [header]
        for r in rows:
            parts.append(format_tender_card(r))
        text = "\n\n".join(parts)
        if len(text) > MAX_MSG_LEN:
            text = text[: MAX_MSG_LEN - 20] + "\n… (обрезано)"

    nav: list[list[InlineKeyboardButton]] = []
    row_nav = [
        InlineKeyboardButton(
            "◀",
            callback_data=f"page:{page - 1}" if page > 1 else "page:noop",
        ),
        InlineKeyboardButton(f"{page}/{pages}", callback_data="page:noop"),
        InlineKeyboardButton(
            "▶",
            callback_data=f"page:{page + 1}" if page < pages else "page:noop",
        ),
    ]
    nav.append(row_nav)
    markup = InlineKeyboardMarkup(nav)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    uid = update.effective_user.id
    register_user(uid, update.effective_user.username or "", update.effective_user.first_name or "")
    _reset(uid)
    kb = [
        [InlineKeyboardButton("Поиск тендеров", callback_data="search:start")],
        [InlineKeyboardButton("Подписка", callback_data="sub:start")],
    ]
    await update.effective_message.reply_text(
        "Подряд PRO — тендеры.\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not update.effective_user:
        return
    await q.answer()
    uid = update.effective_user.id
    data = q.data

    if data == "sub:start":
        _save(uid, action="subscribe", step="niche", niche=None, region=None, nmck_min=None, nmck_max=None, keywords=None)
        kb = [
            [InlineKeyboardButton("Мебель", callback_data="sub:niche:furniture")],
            [InlineKeyboardButton("Стройка / ремонт", callback_data="sub:niche:construction")],
            [InlineKeyboardButton("Свои ключевые слова", callback_data="sub:niche:custom")],
        ]
        await q.edit_message_text("Шаг 1: ниша", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("sub:niche:"):
        niche = data.split(":")[-1]
        _save(uid, step="region" if niche != "custom" else "keywords", niche=niche)
        if niche == "custom":
            await q.edit_message_text("Введите ключевые слова одним сообщением.")
            return
        kb = [
            [InlineKeyboardButton("Москва", callback_data="sub:reg:Москва")],
            [InlineKeyboardButton("СПб", callback_data="sub:reg:Санкт-Петербург")],
            [InlineKeyboardButton("Вся РФ", callback_data="sub:reg:")],
        ]
        await q.edit_message_text("Шаг 3: регион", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("sub:reg:"):
        region = data.split("sub:reg:", 1)[-1]
        _save(uid, step="nmck", region=region or None)
        kb = [
            [InlineKeyboardButton("до 1 млн", callback_data="sub:nm:0:1000000")],
            [InlineKeyboardButton("1–5 млн", callback_data="sub:nm:1000000:5000000")],
            [InlineKeyboardButton("без лимита", callback_data="sub:nm::")],
        ]
        await q.edit_message_text("Шаг 4: диапазон НМЦК", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("sub:nm:"):
        part = data.replace("sub:nm:", "")
        a, _, b = part.partition(":")
        try:
            lo = float(a) if a else None
        except ValueError:
            lo = None
        try:
            hi = float(b) if b else None
        except ValueError:
            hi = None
        _save(uid, step="confirm", nmck_min=lo, nmck_max=hi)
        st2 = _state(uid)
        summary = (
            f"Подтверждение:\n"
            f"Ниша: {st2.get('niche')}\n"
            f"Ключи: {st2.get('keywords') or '—'}\n"
            f"Регион: {st2.get('region') or 'все'}\n"
            f"НМЦК: {lo} — {hi}"
        )
        kb = [[InlineKeyboardButton("Создать подписку", callback_data="sub:ok")], [InlineKeyboardButton("Отмена", callback_data="sub:cancel")]]
        await q.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "sub:ok":
        st = _state(uid)
        url, key = supabase_url(), supabase_key()
        if url and key:
            from supabase import create_client

            cli = create_client(url, key)
            niche_val = st.get("niche")
            kw_raw = st.get("keywords") or ""
            cli.table("subscriptions").insert(
                {
                    "telegram_user_id": uid,
                    "name": str(uid),
                    "niche_tags": [niche_val] if niche_val and niche_val != "custom" else [],
                    "keywords": [k.strip() for k in kw_raw.split(",") if k.strip()] if kw_raw else [],
                    "regions": [st["region"]] if st.get("region") else [],
                    "min_nmck": st.get("nmck_min"),
                    "max_nmck": st.get("nmck_max"),
                    "law_types": [],
                    "okpd2_prefixes": [],
                }
            ).execute()
        _reset(uid)
        await q.edit_message_text("Подписка сохранена.")
        return

    if data == "sub:cancel":
        _reset(uid)
        await q.edit_message_text("Отменено.")
        return

    if data == "search:start":
        _save(uid, action="search", step="q", page=1, filters={})
        await q.edit_message_text("Введите строку поиска (по названию тендера).")
        return

    if data == "page:noop":
        return

    if data.startswith("page:"):
        if data.endswith("noop"):
            return
        try:
            page = int(data.split(":")[1])
        except (IndexError, ValueError):
            return
        st = get_user_state(uid)
        filters_dict = dict(st.get("filters") or {})
        new_state = {**st, "action": "search", "page": page, "filters": filters_dict}
        set_user_state(uid, new_state)
        fl = SearchFilters.from_state_dict(filters_dict, page=page, per_page=5)
        await handle_search_execute(update, context, fl)
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id
    st = _state(uid)
    text = (update.message.text or "").strip()
    if st.get("action") == "subscribe" and st.get("step") == "keywords":
        _save(uid, keywords=text, step="region")
        kb = [
            [InlineKeyboardButton("Москва", callback_data="sub:reg:Москва")],
            [InlineKeyboardButton("Вся РФ", callback_data="sub:reg:")],
        ]
        await update.message.reply_text("Шаг 3: регион", reply_markup=InlineKeyboardMarkup(kb))
        return
    if st.get("action") == "search":
        filters_dict: dict[str, Any] = {
            "query": text,
            "region": st.get("filters", {}).get("region") if isinstance(st.get("filters"), dict) else None,
            "min_nmck": st.get("filters", {}).get("min_nmck") if isinstance(st.get("filters"), dict) else None,
            "max_nmck": st.get("filters", {}).get("max_nmck") if isinstance(st.get("filters"), dict) else None,
            "niche": st.get("filters", {}).get("niche") if isinstance(st.get("filters"), dict) else None,
        }
        new_state = {"action": "search", "step": "results", "page": 1, "filters": filters_dict}
        set_user_state(uid, new_state)
        fl = SearchFilters.from_state_dict(filters_dict, page=1, per_page=5)
        await handle_search_execute(update, context, fl)
        return


def build_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_application().run_polling()


if __name__ == "__main__":
    main()
