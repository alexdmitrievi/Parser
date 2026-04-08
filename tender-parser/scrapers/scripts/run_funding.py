#!/usr/bin/env python3
"""Запуск парсеров программ финансирования МСП (гранты, кредиты, субсидии).

Пример:
    python scrapers/scripts/run_funding.py          # все источники
    python scrapers/scripts/run_funding.py corpmsp  # только Корпорация МСП
    python scrapers/scripts/run_funding.py frprf    # только ФРП
    python scrapers/scripts/run_funding.py mspbank  # только МСП Банк
    python scrapers/scripts/run_funding.py mybusiness
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from shared.config import supabase_key, supabase_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
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
        # Пропустить если нет external_id — не можем дедуплицировать
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


def run_corpmsp() -> int:
    from scrapers.funding_corpmsp import CorpMspScraper
    programs = CorpMspScraper().run()
    saved = _upsert_programs(programs)
    logger.info("corpmsp: %d programs saved", saved)
    return saved


def run_frprf() -> int:
    from scrapers.funding_frprf import FrprfScraper
    programs = FrprfScraper().run()
    saved = _upsert_programs(programs)
    logger.info("frprf: %d programs saved", saved)
    return saved


def run_mspbank() -> int:
    from scrapers.funding_mspbank import MspBankScraper
    programs = MspBankScraper().run()
    saved = _upsert_programs(programs)
    logger.info("mspbank: %d programs saved", saved)
    return saved


def run_mybusiness() -> int:
    from scrapers.funding_mybusiness import MyBusinessScraper
    programs = MyBusinessScraper().run()
    saved = _upsert_programs(programs)
    logger.info("mybusiness: %d programs saved", saved)
    return saved


SOURCES = {
    "corpmsp": run_corpmsp,
    "frprf": run_frprf,
    "mspbank": run_mspbank,
    "mybusiness": run_mybusiness,
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

    total = 0
    if args.source == "all":
        for name, fn in SOURCES.items():
            logger.info("--- Running %s ---", name)
            try:
                total += fn()
            except Exception:
                logger.exception("source %s failed", name)
    else:
        total += SOURCES[args.source]()

    logger.info("=== Total saved: %d ===", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
