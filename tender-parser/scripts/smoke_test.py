"""Проверка окружения: Supabase + Telegram Bot API + DB health.

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
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"FAIL: missing env {name}")
        sys.exit(1)
    return v


def main() -> None:
    errors = 0
    token = _require_env("TELEGRAM_BOT_TOKEN")

    from shared.config import supabase_key, supabase_url
    from shared.db import get_db, get_stats_via_rpc, get_scrape_health

    if not supabase_url():
        print("FAIL: set SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL")
        sys.exit(1)
    if not supabase_key():
        print("FAIL: set SUPABASE_KEY or SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY")
        sys.exit(1)

    # 1. DB connection
    db_ok = False
    try:
        db = get_db()
        result = db.table("tenders").select("id", count="exact").limit(1).execute()
        n = result.count if result.count is not None else 0
        print(f"PASS: Supabase tenders count = {n}")
        db_ok = True
    except Exception as e:
        print(f"FAIL: Supabase connection: {e}")
        if "Name or service not known" in str(e) or "getaddrinfo" in str(e):
            print(
                "      Хост из SUPABASE_URL не резолвится. Обычно это значит, "
                "что проект Supabase удалён либо приостановлен, или в секрете "
                "SUPABASE_URL опечатка. Проверьте Supabase → Project Settings → API."
            )
        errors += 1

    # 2. Stats RPC (DB-side aggregation)
    try:
        stats = get_stats_via_rpc()
        total = stats.get("total", 0)
        platforms = stats.get("platforms", 0)
        print(f"PASS: Stats RPC — {total} tenders from {platforms} platforms")
    except Exception as e:
        print(f"WARN: Stats RPC: {e} (run migration_v4.sql to enable)")
        # Not critical — fallback works

    # 3. Scrape log
    #
    # get_scrape_health() глушит ошибки внутри и возвращает пустой список,
    # поэтому без проверки db_ok этот пункт печатал "PASS: 0 entries" даже
    # когда база вообще недоступна — то есть health-проверка врала ровно в
    # той ситуации, ради которой она и нужна.
    if not db_ok:
        print("SKIP: Scrape log — база недоступна, проверять нечего")
    else:
        try:
            logs = get_scrape_health()
            print(f"PASS: Scrape log — {len(logs)} entries")
        except Exception as e:
            print(f"WARN: Scrape log: {e}")

    # 4. Telegram Bot API
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with httpx.Client(timeout=15) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
        if not data.get("ok"):
            print(f"FAIL: Telegram getMe: {data}")
            errors += 1
        else:
            uname = (data.get("result") or {}).get("username", "?")
            print(f"PASS: Telegram bot @{uname}")
    except Exception as e:
        print(f"FAIL: Telegram API: {e}")
        errors += 1

    if errors:
        print(f"\n{errors} check(s) failed")
        sys.exit(1)
    else:
        print("\nAll checks passed")


if __name__ == "__main__":
    main()
