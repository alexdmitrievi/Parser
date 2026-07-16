"""Минимальный Telegram-клиент для мониторинга (один получатель).

Не тянет python-telegram-bot: для отправки карточек и сервисных алертов
достаточно Bot API поверх httpx с ретраями.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger("monitor.telegram")


def get_owner_chat_id() -> Optional[int]:
    raw = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    try:
        return int(raw)
    except ValueError:
        return None


def send_message(
    text: str,
    chat_id: Optional[int] = None,
    parse_mode: str = "HTML",
    retries: int = 3,
) -> bool:
    """Отправить сообщение владельцу. Ретраи с бэкоффом 2s/4s/8s."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or get_owner_chat_id()
    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    delay = 2.0
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:
                retry_after = float(resp.json().get("parameters", {}).get("retry_after", delay))
                logger.warning(f"Telegram rate limit, sleeping {retry_after}s")
                time.sleep(retry_after)
                continue
            logger.warning(f"Telegram API error {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            logger.warning(f"Telegram send attempt {attempt} failed: {e}")
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    return False
