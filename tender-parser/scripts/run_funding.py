#!/usr/bin/env python3
"""Запуск парсеров программ финансирования МСП (гранты, кредиты, субсидии).

Пример:
    python scripts/run_funding.py          # все источники
    python scripts/run_funding.py corpmsp  # только Корпорация МСП
    python scripts/run_funding.py frprf    # только ФРП
    python scripts/run_funding.py mspbank  # только МСП Банк
    python scripts/run_funding.py mybusiness
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from shared.config import supabase_key, supabase_url
from shared.db import log_scrape_start, log_scrape_finish

from shared.logging_config import configure_logging
configure_logging()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=False)
logger = logging.getLogger(__name__)


def _upsert_programs(programs: list[dict[str, Any]]) -> int:
    """Сохранить программы в Supabase с upsert по (source_platform, external_id)."""
    from supabase import create_client
    url, key = supabase_url(), supabase_key()
    if not url or not key:
        logger.error("SUPABASE_URL or SUPABASE_KEY not set")
        return 0

    cli = create_client(url, key)
    saved = 0
    for prog in programs:
        if not prog.get("external_id"):
            prog["external_id"] = f"auto-{hash(prog.get('original_url','')) % 1_000_000}"

        try:
            cli.table("funding_programs").upsert(
                prog,
                on_conflict="source_platform,external_id",
            ).execute()
            saved += 1
        except Exception as e:
            logger.warning("upsert failed [%s / %s]: %s",
                           prog.get("source_platform"), prog.get("external_id"), e)
    return saved


def preflight_db() -> bool:
    """Проверить, что база доступна, до запуска скрейперов.

    Без этой проверки прогон при недоступной базе не падает быстро: каждый
    источник честно скачивает выдачу, а затем спотыкается на сохранении,
    ретраит с бэкоффом и идёт к следующему. На полном наборе это выедает
    весь timeout-minutes и job убивается по таймауту, ничего не сохранив.
    Дешевле проверить один раз и выйти с понятным сообщением.
    """
    from shared.db import get_db

    try:
        get_db().table("tenders").select("id", count="exact").limit(1).execute()
        return True
    except Exception as e:
        logger.error("База недоступна, парсинг не запускается: %s", e)
        if "Name or service not known" in str(e) or "getaddrinfo" in str(e):
            logger.error(
                "Хост из SUPABASE_URL не резолвится — проект Supabase удалён "
                "или приостановлен, либо в секрете опечатка. "
                "Проверьте Supabase → Project Settings → API."
            )
        return False


def _run_with_log(runner_fn, name: str) -> int:
    """Запустить runner с записью в scrape_log."""
    log_id = log_scrape_start(name, "funding")
    t0 = time.time()
    try:
        count = runner_fn()
        duration_ms = int((time.time() - t0) * 1000)
        log_scrape_finish(log_id, "success", tenders_found=count, tenders_inserted=count, duration_ms=duration_ms)
        logger.info("%s: %d programs saved", name, count)
        return count
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        log_scrape_finish(log_id, "failed", error_message=str(e)[:500], duration_ms=duration_ms)
        logger.exception("source %s failed", name)
        return 0


def run_corpmsp() -> int:
    from scrapers.funding_corpmsp import CorpMspScraper
    return _upsert_programs(CorpMspScraper().run())


def run_frprf() -> int:
    from scrapers.funding_frprf import FrprfScraper
    return _upsert_programs(FrprfScraper().run())


def run_mspbank() -> int:
    from scrapers.funding_mspbank import MspBankScraper
    return _upsert_programs(MspBankScraper().run())


def run_mybusiness() -> int:
    from scrapers.funding_mybusiness import MyBusinessScraper
    return _upsert_programs(MyBusinessScraper().run())


SOURCES = {
    "corpmsp": (run_corpmsp, "corpmsp"),
    "frprf": (run_frprf, "frprf"),
    "mspbank": (run_mspbank, "mspbank"),
    "mybusiness": (run_mybusiness, "mybusiness"),
}


def main() -> int:
    p = argparse.ArgumentParser(description="Run funding program scrapers")
    p.add_argument(
        "source",
        nargs="?",
        default="all",
        choices=list(SOURCES.keys()) + ["all"],
        help="Источник: corpmsp | frprf | mspbank | mybusiness | all",
    )
    args = p.parse_args()

    if not preflight_db():
        return 1

    total = 0
    if args.source == "all":
        for name, (fn, label) in SOURCES.items():
            logger.info("--- Running %s ---", name)
            total += _run_with_log(fn, label)
    else:
        fn, label = SOURCES[args.source]
        total += _run_with_log(fn, label)

    logger.info("=== Total saved: %d ===", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
