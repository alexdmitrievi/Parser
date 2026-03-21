#!/usr/bin/env python3
"""Запуск парсеров по группам и сохранение в Supabase (dict-строки + дедупликация).

Использует пакет `scrapers` из `tender-parser/scripts/scrapers/` (расширенные площадки),
при необходимости — основной `scrapers/` в корне. Корень проекта — `parents[2]` от
этого файла (`.../scrapers/scripts/run_parser.py` → `tender-parser/`).

Пример:
    python scrapers/scripts/run_parser.py eis_api
    python scrapers/scripts/run_parser.py eis_ftp
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[2]
# Сначала scripts/ — там полный набор парсеров (fabrikant, etpgpb, …); затем корень — pipeline, shared.
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from pipeline.deduplicator import prepare_for_insert
from pipeline.scraper_row import normalize_tender, tag_tender
from shared.db import fetch_tender_by_registry, upsert_tender

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _process_and_save(items: list[dict[str, Any]], label: str) -> int:
    saved = 0
    for raw in items:
        n = normalize_tender(raw)
        if not n:
            continue
        n = tag_tender(n)
        reg = str(n.get("registry_number") or "")
        existing = fetch_tender_by_registry(reg) if reg else None
        existing_map = {reg: existing} if existing else {}
        payload, action = prepare_for_insert(n, existing_map)
        if not payload or action == "skip":
            continue
        try:
            upsert_tender(payload)
            saved += 1
        except Exception as e:
            logger.warning("upsert failed %s: %s", reg, e)
    logger.info("%s: processed %s, saved/merged ~%s rows", label, len(items), saved)
    return saved


def run_fabrikant() -> int:
    from scrapers.fabrikant import FabrikantScraper

    return _process_and_save(FabrikantScraper().run(), "fabrikant")


def run_etpgpb() -> int:
    from scrapers.etpgpb import EtpgpbScraper

    return _process_and_save(EtpgpbScraper().run(), "etpgpb")


def run_etp_ets() -> int:
    from scrapers.etp_ets import EtpEtsScraper

    return _process_and_save(EtpEtsScraper().run(), "etp_ets")


def run_tenderpro() -> int:
    from scrapers.tenderpro import TenderproScraper

    return _process_and_save(TenderproScraper().run(), "tenderpro")


def run_lot_online() -> int:
    from scrapers.lot_online import LotOnlineScraper

    return _process_and_save(LotOnlineScraper().run(), "lot_online")


def run_zakupki_mos() -> int:
    from scrapers.zakupki_mos import ZakupkiMosScraper

    return _process_and_save(ZakupkiMosScraper().run(), "zakupki_mos")


def run_eis_api() -> int:
    from scrapers.eis_api import EisApiScraper

    return _process_and_save(EisApiScraper().run(), "EIS API")


def run_eis_223() -> int:
    from scrapers.eis_api import EisApiScraper

    return _process_and_save(EisApiScraper().run_223(), "EIS 223-FZ")


def run_eis_ftp() -> int:
    from scrapers.eis_ftp import EisFtpScraper

    return _process_and_save(EisFtpScraper().run(), "EIS FTP 44")


def run_eis_ftp_223() -> int:
    from scrapers.eis_ftp import EisFtpScraper

    return _process_and_save(EisFtpScraper().run_223(), "EIS FTP 223")


GROUPS: dict[str, list[Callable[[], int]]] = {
    "commercial": [run_fabrikant, run_tenderpro],
    "etp": [run_etpgpb, run_etp_ets, run_lot_online],
    "regional": [run_zakupki_mos],
    "eis_api": [run_eis_api, run_eis_223],
    "all": [
        run_fabrikant,
        run_tenderpro,
        run_etpgpb,
        run_etp_ets,
        run_lot_online,
        run_zakupki_mos,
        run_eis_api,
        run_eis_223,
    ],
}


def main() -> int:
    p = argparse.ArgumentParser(description="Run tender scrapers (dict row pipeline)")
    p.add_argument(
        "group",
        nargs="?",
        default="all",
        choices=list(GROUPS.keys()) + ["eis_ftp"],
        help="Parser group",
    )
    args = p.parse_args()
    total = 0
    if args.group == "eis_ftp":
        total += run_eis_ftp()
        total += run_eis_ftp_223()
        return 0 if total >= 0 else 1
    for fn in GROUPS[args.group]:
        total += fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
