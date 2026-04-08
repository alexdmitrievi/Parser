"""Конфигурация проекта. Все настройки через переменные окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class NichePreset:
    """Пресет для ниши (мебель, подряды и т.д.)."""
    name: str
    tag: str
    keywords: list[str]
    okpd2_prefixes: list[str]
    priority_regions: list[str]


# --- Пресеты ниш ---

NICHE_FURNITURE = NichePreset(
    name="Мебель",
    tag="furniture",
    keywords=[
        "мебель", "диван", "кресло", "мягкая мебель", "обивка", "перетяжка",
        "мебель на заказ", "офисная мебель", "мебель для учреждений",
        "поставка мебели", "изготовление мебели", "шкаф", "стол", "стул",
        "кровать", "тумба", "комод", "стеллаж",
    ],
    okpd2_prefixes=["31.0", "31.1", "31.2", "31.9"],
    priority_regions=["Омская область", "Новосибирская область", "Тюменская область"],
)

NICHE_CONSTRUCTION = NichePreset(
    name="Подряды",
    tag="construction",
    keywords=[
        "подряд", "субподряд", "строительные работы", "ремонт", "отделка",
        "капитальный ремонт", "текущий ремонт", "строительно-монтажные работы",
        "СМР", "благоустройство", "содержание", "обслуживание зданий",
        "реконструкция", "демонтаж", "фасад", "кровля", "сантехника",
    ],
    okpd2_prefixes=["41.2", "42.", "43.", "71.1", "81.1"],
    priority_regions=[],
)

ALL_NICHES = [NICHE_FURNITURE, NICHE_CONSTRUCTION]


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def supabase_url() -> str:
    """URL проекта Supabase (для скриптов и status updater)."""
    return get_env("SUPABASE_URL") or get_env("NEXT_PUBLIC_SUPABASE_URL")


def supabase_key() -> str:
    """Ключ Supabase: для админ-скриптов сначала service role, иначе anon/SUPABASE_KEY."""
    return (
        get_env("SUPABASE_SERVICE_ROLE_KEY")
        or get_env("SUPABASE_KEY")
        or get_env("SUPABASE_ANON_KEY")
    )


def get_config() -> dict:
    """Те же URL/ключи, что и в routes_tenders / веб-роутерах (fallback SERVICE_ROLE / ANON)."""
    return {
        "telegram_bot_token": get_env("TELEGRAM_BOT_TOKEN"),
        "supabase_url": supabase_url(),
        "supabase_key": supabase_key(),
        "eis_ftp_host": get_env("EIS_FTP_HOST", "ftp.zakupki.gov.ru"),
        "scraping_bee_api_key": get_env("SCRAPING_BEE_API_KEY"),
        "log_level": get_env("LOG_LEVEL", "INFO"),
        "bot_webhook_secret": get_env("BOT_WEBHOOK_SECRET", ""),
        "max_free_subscriptions": int(get_env("MAX_FREE_SUBSCRIPTIONS", "3")),
    }
