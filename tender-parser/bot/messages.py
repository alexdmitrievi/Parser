"""Шаблоны сообщений и форматирование карточек тендеров."""

from __future__ import annotations

from shared.constants import LAW_TYPES, PURCHASE_METHODS


def format_price(nmck: float | None) -> str:
    """Форматировать цену: 1250000 → 1 250 000 ₽"""
    if nmck is None:
        return "не указана"
    if nmck >= 1_000_000:
        return f"{nmck:,.0f} ₽".replace(",", " ")
    elif nmck >= 1_000:
        return f"{nmck:,.0f} ₽".replace(",", " ")
    else:
        return f"{nmck:.2f} ₽"


def format_deadline(deadline: str | None) -> str:
    """Форматировать дедлайн."""
    if not deadline:
        return "не указана"
    # Обрезаем до даты
    return deadline[:10] if len(deadline) >= 10 else deadline


def format_law_type(law_type: str | None) -> str:
    return LAW_TYPES.get(law_type, law_type or "—")


def format_tender_card(tender: dict) -> str:
    """Форматировать карточку тендера для Telegram (HTML)."""
    title = tender.get("title", "Без названия")
    if len(title) > 200:
        title = title[:197] + "..."

    nmck = format_price(tender.get("nmck"))
    law = format_law_type(tender.get("law_type"))
    method = tender.get("purchase_method", "")
    customer = tender.get("customer_name", "—")
    if len(customer) > 80:
        customer = customer[:77] + "..."
    region = tender.get("customer_region", "—")
    deadline = format_deadline(tender.get("submission_deadline"))
    url = tender.get("original_url", "")

    # Тег ниши
    niches = tender.get("niche_tags") or []
    niche_emoji = ""
    if "furniture" in niches:
        niche_emoji = "🛋"
    elif "construction" in niches:
        niche_emoji = "🏗"

    lines = [
        f"📋 <b>{title}</b>",
        "",
        f"💰 НМЦК: {nmck}",
        f"📊 {law} | {method}" if method else f"📊 {law}",
        f"🏢 {customer}",
        f"📍 {region}",
        f"⏰ Подача до: {deadline}",
    ]

    if niche_emoji:
        lines.append(f"{niche_emoji} {', '.join(niches)}")

    if url:
        lines.append(f'\n🔗 <a href="{url}">Открыть на площадке</a>')

    return "\n".join(lines)


def format_tender_list(tenders: list[dict], page: int, total: int, per_page: int = 5) -> str:
    """Форматировать список тендеров с пагинацией."""
    if not tenders:
        return "🔍 По вашему запросу ничего не найдено."

    total_pages = (total + per_page - 1) // per_page
    header = f"📑 Результаты ({page}/{total_pages}, всего: {total}):\n\n"

    cards = []
    for i, t in enumerate(tenders, start=1):
        cards.append(f"<b>{(page - 1) * per_page + i}.</b>\n{format_tender_card(t)}")

    return header + "\n\n━━━━━━━━━━━━━━━\n\n".join(cards)


WELCOME_MESSAGE = """👋 <b>Привет! Я — Парсер Тендеров.</b>

Помогу найти тендеры по вашему бизнесу и буду присылать новые автоматически.

<b>Что умею:</b>
🔍 Искать тендеры по ключевым словам, регионам и НМЦК
📋 Создавать подписки — присылаю новые тендеры автоматически
🔥 Показывать горячие тендеры (дедлайн &lt; 3 дней)

<b>Площадки:</b> ЕИС (44-ФЗ, 223-ФЗ), Сбербанк-АСТ, РТС-тендер, B2B-Center и другие.

Выберите действие:"""


HELP_MESSAGE = """<b>📖 Справка</b>

<b>Команды:</b>
/start — Главное меню
/search — Поиск тендеров
/subscribe — Создать подписку
/mysubs — Мои подписки
/hot — Горячие тендеры (дедлайн &lt; 3 дней)
/help — Эта справка

<b>Подписки:</b>
Создайте подписку с фильтрами (ниша, регион, цена) и бот будет автоматически присылать подходящие тендеры.

Бесплатный лимит: 3 подписки."""
