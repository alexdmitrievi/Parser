#!/usr/bin/env python3
"""Smoke test: проверка компонентов перед деплоем."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_config() -> None:
    """Проверить что env-переменные заданы."""
    from shared.config import get_config

    cfg = get_config()
    assert cfg.get("supabase_url"), "SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL not set"
    assert cfg.get("supabase_key"), "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY not set"
    assert cfg.get("telegram_bot_token"), "TELEGRAM_BOT_TOKEN not set"
    print("✅ Config OK")


def test_db_connection() -> None:
    """Проверить подключение к Supabase."""
    from shared.db import get_db

    db = get_db()
    result = db.table("tenders").select("id").limit(1).execute()
    n = len(result.data or [])
    print(f"✅ DB OK — tenders table, {n} row(s) in sample")


def test_search() -> None:
    """Проверить поиск."""
    from shared.db import search_tenders
    from shared.models import SearchFilters

    results = search_tenders(SearchFilters(query="мебель", per_page=3, page=1))
    print(f"✅ Search OK — got {len(results)} result(s) for 'мебель'")


def test_bot_message() -> None:
    """Проверить форматирование сообщений бота."""
    from bot.messages import format_tender_card

    card = format_tender_card(
        {
            "title": "Тестовый тендер",
            "nmck": 1500000,
            "law_type": "44-fz",
            "customer_name": "ГБУЗ Омской области",
            "customer_region": "Омская область",
            "submission_deadline": "2026-04-01",
            "original_url": "https://zakupki.gov.ru/test",
            "niche_tags": ["furniture"],
        }
    )
    assert "Тестовый тендер" in card
    assert "1 500 000" in card
    print("✅ Bot messages OK")


def test_scraper_import() -> None:
    """Проверить импорт парсеров (есть в репозитории)."""
    scrapers = [
        "scrapers.eis_ftp",
        "scrapers.eis_api",
        "scrapers.tektorg",
        "scrapers.fabrikant",
        "scrapers.etpgpb",
        "scrapers.etp_ets",
        "scrapers.tenderpro",
        "scrapers.lot_online",
        "scrapers.zakupki_mos",
    ]
    failed = 0
    for name in scrapers:
        try:
            __import__(name)
            print(f"  ✅ {name}")
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
    if failed:
        raise RuntimeError(f"{failed} scraper import(s) failed")
    print("✅ Scrapers import OK")


def main() -> int:
    tests = [
        test_config,
        test_db_connection,
        test_search,
        test_bot_message,
        test_scraper_import,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Results: {len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
