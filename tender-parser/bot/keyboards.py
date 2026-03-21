"""Inline-клавиатуры для Telegram-бота."""

from __future__ import annotations

import json
from shared.constants import POPULAR_REGIONS, NMCK_RANGES


def inline_button(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def inline_keyboard(rows: list[list[dict]]) -> dict:
    return {"inline_keyboard": rows}


# ──────── Главное меню ────────

MAIN_MENU = inline_keyboard([
    [inline_button("🔍 Поиск тендеров", "search:start")],
    [inline_button("📋 Мои подписки", "mysubs"), inline_button("🔥 Горячие", "hot")],
    [inline_button("⚙️ Настройки", "settings"), inline_button("📖 Справка", "help")],
])

# ──────── Выбор ниши ────────

NICHE_KEYBOARD = inline_keyboard([
    [inline_button("🛋 Мебель", "niche:furniture"), inline_button("🏗 Подряды", "niche:construction")],
    [inline_button("🔎 Свой запрос", "niche:custom")],
    [inline_button("« Назад", "main_menu")],
])

# ──────── Выбор региона ────────

def region_keyboard() -> dict:
    rows = []
    for i in range(0, len(POPULAR_REGIONS), 2):
        row = [inline_button(POPULAR_REGIONS[i], f"region:{POPULAR_REGIONS[i]}")]
        if i + 1 < len(POPULAR_REGIONS):
            row.append(inline_button(POPULAR_REGIONS[i + 1], f"region:{POPULAR_REGIONS[i + 1]}"))
        rows.append(row)
    rows.append([inline_button("🌍 Все регионы", "region:all")])
    rows.append([inline_button("« Назад", "search:start")])
    return inline_keyboard(rows)


# ──────── Выбор НМЦК ────────

NMCK_KEYBOARD = inline_keyboard([
    [inline_button("до 500К", "nmck:0-500000"), inline_button("500К — 5М", "nmck:500000-5000000")],
    [inline_button("5М — 50М", "nmck:5000000-50000000"), inline_button("50М+", "nmck:50000000-0")],
    [inline_button("💰 Любая", "nmck:any")],
    [inline_button("« Назад", "search:niche")],
])

# ──────── Пагинация ────────

def pagination_keyboard(page: int, total_pages: int, prefix: str = "page") -> dict:
    buttons = []
    if page > 1:
        buttons.append(inline_button("◀", f"{prefix}:{page - 1}"))
    buttons.append(inline_button(f"{page}/{total_pages}", "noop"))
    if page < total_pages:
        buttons.append(inline_button("▶", f"{prefix}:{page + 1}"))
    
    rows = [buttons]
    rows.append([inline_button("🔄 Новый поиск", "search:start"), inline_button("📋 Подписаться", "sub:from_search")])
    return inline_keyboard(rows)


# ──────── Подписки ────────

def subscription_list_keyboard(subs: list[dict]) -> dict:
    rows = []
    for sub in subs:
        name = sub.get("name", "Без имени")
        sub_id = sub["id"]
        rows.append([
            inline_button(f"📋 {name}", f"sub_detail:{sub_id}"),
            inline_button("❌", f"sub_delete:{sub_id}"),
        ])
    rows.append([inline_button("➕ Новая подписка", "subscribe:start")])
    rows.append([inline_button("« Главное меню", "main_menu")])
    return inline_keyboard(rows)


# ──────── Подтверждение подписки ────────

def confirm_subscription_keyboard() -> dict:
    return inline_keyboard([
        [inline_button("✅ Создать подписку", "sub_confirm:yes")],
        [inline_button("❌ Отмена", "sub_confirm:no")],
    ])
