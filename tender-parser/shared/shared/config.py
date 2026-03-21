"""Переменные окружения."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache
def supabase_url() -> str | None:
    return os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")


@lru_cache
def supabase_key() -> str | None:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")


def get_config() -> dict[str, Any]:
    """Конфиг для smoke-тестов и диагностики."""
    return {
        "supabase_url": supabase_url() or "",
        "supabase_key": supabase_key() or "",
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN") or "",
    }
