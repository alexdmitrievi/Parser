"""Telegram-бот мониторинга: один пользователь, авторизация по chat_id.

Бот отвечает ТОЛЬКО владельцу (TELEGRAM_CHAT_ID из .env), остальные
сообщения молча игнорируются. Существующая многопользовательская система
подписок (bot/handler.py, Supabase) не используется и не изменяется —
этот бот работает поверх локального PostgreSQL.

Команды:
    /start  — краткая справка
    /stats  — сводка за 30 дней (ниши, медианное снижение, топ-5 победителей)
    /status — состояние последнего цикла мониторинга

Запуск (systemd service):
    python -m monitor.bot
"""

from __future__ import annotations

import html
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.env import load_dotenv  # noqa: E402

load_dotenv()

from telegram import Update  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application, CommandHandler, ContextTypes, MessageHandler, filters,
)

from engine.persistence.postgres_repo import PostgresTenderRepository  # noqa: E402
from monitor.telegram_client import get_owner_chat_id  # noqa: E402

logger = logging.getLogger("monitor.bot")


def _is_owner(update: Update) -> bool:
    owner = get_owner_chat_id()
    chat = update.effective_chat
    return bool(owner and chat and chat.id == owner)


def _fmt_money(v) -> str:
    if v is None:
        return "—"
    return f"{int(round(float(v))):,}".replace(",", " ") + " ₽"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await update.effective_message.reply_text(
        "Мониторинг закупок «Подряд ПРО».\n\n"
        "Карточки по новым закупкам приходят автоматически (цикл — 120 минут).\n"
        "Фильтры: config/filters.yaml на сервере.\n\n"
        "Команды:\n"
        "/stats — сводка за 30 дней\n"
        "/status — состояние последнего цикла"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    repo = PostgresTenderRepository()
    try:
        stats = repo.stats_last_days(30)
    except Exception as e:
        logger.error(f"/stats failed: {e}")
        await update.effective_message.reply_text(f"Ошибка получения статистики: {e}")
        return
    finally:
        repo.close()

    lines = ["📊 <b>Сводка за 30 дней</b>", ""]
    lines.append(f"Закупок собрано: {stats['tenders_total']}")
    lines.append(f"Прошло фильтры: {stats['tenders_matched']}")

    by_niche = stats.get("by_niche") or {}
    if by_niche:
        lines.append("")
        lines.append("<b>По нишам:</b>")
        for tag, count in list(by_niche.items())[:8]:
            lines.append(f"  • {tag}: {count}")

    lines.append("")
    lines.append(f"Протоколов итогов: {stats.get('protocols_count', 0)}")
    median = stats.get("median_reduction_pct")
    lines.append(
        f"Медианное снижение цены: {median:.1f}%" if median is not None
        else "Медианное снижение цены: — (протоколов пока нет)"
    )

    winners = stats.get("top_winners") or []
    if winners:
        lines.append("")
        lines.append("<b>Топ-5 победителей:</b>")
        for w in winners:
            name = html.escape(w.get("winner_name") or "—")
            inn = w.get("winner_inn") or "—"
            region = w.get("region") or "—"
            lines.append(
                f"  • {name} (ИНН {inn}, {region}) — "
                f"{w['wins']} побед, {_fmt_money(w.get('total_price'))}"
            )

    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="HTML", disable_web_page_preview=True,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    repo = PostgresTenderRepository()
    try:
        last = repo.get_state("last_cycle")
    except Exception as e:
        await update.effective_message.reply_text(f"БД недоступна: {e}")
        return
    finally:
        repo.close()

    if not last:
        await update.effective_message.reply_text("Циклы ещё не запускались.")
        return

    lines = ["🩺 <b>Последний цикл</b>", ""]
    lines.append(f"Начало: {last.get('started_at', '—')}")
    lines.append(f"Конец: {last.get('finished_at', '—')}")
    for source, info in (last.get("summary") or {}).items():
        lines.append(f"  • {source}: {info}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def ignore_others(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Не-владельцам не отвечаем вообще."""
    if not _is_owner(update):
        return


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not get_owner_chat_id():
        raise RuntimeError("TELEGRAM_CHAT_ID is not set — bot refuses to start")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.ALL, ignore_others))
    logger.info("Single-user bot started (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
