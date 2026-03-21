"""Скрипт установки Telegram webhook.

Использование:
    python scripts/setup_webhook.py https://your-project.vercel.app/api/webhook
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from shared.config import get_config


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/setup_webhook.py <WEBHOOK_URL>")
        print("Example: python scripts/setup_webhook.py https://my-tender-bot.vercel.app/api/webhook")
        sys.exit(1)

    webhook_url = sys.argv[1]
    cfg = get_config()
    token = cfg["telegram_bot_token"]

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    # Установить webhook
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    resp = httpx.post(url, json={"url": webhook_url})
    print(f"setWebhook response: {resp.json()}")

    # Проверить
    info_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    resp = httpx.get(info_url)
    print(f"Webhook info: {resp.json()}")


if __name__ == "__main__":
    main()
