"""Проверка окружения: Supabase + Telegram Bot API.

Запуск из каталога tender-parser:
    export SUPABASE_URL=...
    export SUPABASE_KEY=...
    export TELEGRAM_BOT_TOKEN=...
    pip install -r requirements-parser.txt
    python scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"FAIL: missing env {name}")
        sys.exit(1)
    return v


def main() -> None:
    _require_env("SUPABASE_URL")
    _require_env("SUPABASE_KEY")
    token = _require_env("TELEGRAM_BOT_TOKEN")

    from shared.db import get_db

    db = get_db()
    result = db.table("tenders").select("id", count="exact").limit(1).execute()
    n = result.count if result.count is not None else 0
    print(f"OK: Supabase tenders count = {n}")

    url = f"https://api.telegram.org/bot{token}/getMe"
    with httpx.Client(timeout=15) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    if not data.get("ok"):
        print(f"FAIL: Telegram getMe: {data}")
        sys.exit(1)
    uname = (data.get("result") or {}).get("username", "?")
    print(f"OK: Telegram bot @{uname}")


if __name__ == "__main__":
    main()
