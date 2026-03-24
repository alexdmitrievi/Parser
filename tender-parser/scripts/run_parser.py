"""Entry point для GitHub Actions: запуск парсеров.

Использование:
    python scripts/run_parser.py --source eis_ftp
    python scripts/run_parser.py --source eis_api
    python scripts/run_parser.py --source commercial
    python scripts/run_parser.py --source etp
    python scripts/run_parser.py --source all
"""

from __future__ import annotations

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import insert_tenders
from pipeline.normalizer import normalize_batch
from pipeline.tagger import tag_tenders_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("parser")


def _process_and_save(tenders, source_name: str) -> int:
    """Нормализовать, протегировать и сохранить тендеры."""
    if not tenders:
        logger.info(f"{source_name}: no tenders found")
        return 0
    tenders = normalize_batch(tenders)
    tenders = tag_tenders_batch(tenders)
    count = insert_tenders(tenders)
    logger.info(f"{source_name}: saved {count} tenders")
    return count


# ──────── ЕИС ────────

def run_eis_ftp() -> int:
    from scrapers.eis_ftp import EisFtpScraper
    logger.info("=== EIS FTP ===")
    scraper = EisFtpScraper()
    return _process_and_save(scraper.run(max_files_per_region=30), "EIS FTP")


def run_eis_api() -> int:
    from scrapers.eis_api import EisApiScraper
    logger.info("=== EIS API ===")
    scraper = EisApiScraper()
    return _process_and_save(
        scraper.run(
            queries=[
                "ремонт помещений", "строительные работы", "поставка оборудования",
                "оказание услуг", "IT услуги", "медицинское оборудование",
                "мебель", "транспортные услуги", "благоустройство",
                "продукты питания", "техническое обслуживание",
                "проектные работы", "клининг", "охранные услуги",
                "электромонтажные работы",
            ],
            max_pages=2,
        ),
        "EIS API",
    )


# ──────── Федеральные ЭТП ────────

def run_roseltorg() -> int:
    from scrapers.roseltorg import RoseltorgScraper
    logger.info("=== Roseltorg ===")
    scraper = RoseltorgScraper()
    return _process_and_save(scraper.run(), "Roseltorg")


def run_sberbank_ast() -> int:
    from scrapers.sberbank_ast import SberbankAstScraper
    logger.info("=== Sberbank-AST ===")
    scraper = SberbankAstScraper()
    return _process_and_save(scraper.run(), "Sberbank-AST")


def run_rts_tender() -> int:
    from scrapers.rts_tender import RtsTenderScraper
    logger.info("=== RTS-Tender ===")
    scraper = RtsTenderScraper()
    return _process_and_save(scraper.run(), "RTS-Tender")


def run_tektorg() -> int:
    from scrapers.tektorg import TekTorgScraper
    logger.info("=== TekTorg ===")
    scraper = TekTorgScraper()
    return _process_and_save(scraper.run(), "TekTorg")


# ──────── Коммерческие ────────

def run_b2b_center() -> int:
    from scrapers.b2b_center import B2BCenterScraper
    logger.info("=== B2B-Center ===")
    scraper = B2BCenterScraper()
    return _process_and_save(scraper.run(), "B2B-Center")


def run_tenderguru() -> int:
    from scrapers.tenderguru import TenderGuruScraper
    logger.info("=== TenderGuru ===")
    scraper = TenderGuruScraper()
    return _process_and_save(
        scraper.run(
            queries=["мебель поставка", "подряд строительство",
                     "ремонт помещений", "изготовление мебели"],
            max_pages=3,
        ),
        "TenderGuru",
    )


# ──────── Агрегаторы ────────

def run_rostender() -> int:
    from scrapers.rostender import RostenderScraper
    logger.info("=== Rostender ===")
    scraper = RostenderScraper()
    return _process_and_save(scraper.run(), "Rostender")


# ──────── Playwright-парсеры ────────

def run_tektorg_pw() -> int:
    from scrapers.tektorg_pw import TekTorgPlaywrightScraper
    logger.info("=== TekTorg (Playwright) ===")
    scraper = TekTorgPlaywrightScraper()
    return _process_and_save(scraper.run(max_pages=2), "TekTorg PW")


def run_fabrikant_pw() -> int:
    from scrapers.fabrikant_pw import FabrikantPlaywrightScraper
    logger.info("=== Fabrikant (Playwright) ===")
    scraper = FabrikantPlaywrightScraper()
    return _process_and_save(scraper.run(max_pages=2), "Fabrikant PW")


def run_sberbank_ast_pw() -> int:
    from scrapers.sberbank_ast_pw import SberbankAstPlaywrightScraper
    logger.info("=== Sberbank-AST (Playwright) ===")
    scraper = SberbankAstPlaywrightScraper()
    return _process_and_save(scraper.run(), "Sberbank-AST PW")


# ──────── Группы ────────

GROUPS = {
    "eis_ftp": [run_eis_ftp],
    "eis_api": [run_eis_api],
    "roseltorg": [run_roseltorg],
    "etp": [run_roseltorg, run_sberbank_ast, run_rts_tender, run_tektorg],
    "commercial": [run_b2b_center, run_rostender, run_tenderguru],
    "rostender": [run_rostender],
    "playwright": [run_tektorg_pw, run_fabrikant_pw, run_sberbank_ast_pw],
    "all": [run_eis_ftp, run_eis_api, run_roseltorg, run_sberbank_ast,
            run_rts_tender, run_tektorg, run_b2b_center, run_tenderguru],
}


def main():
    parser = argparse.ArgumentParser(description="Tender Parser Runner")
    parser.add_argument(
        "--source",
        choices=list(GROUPS.keys()),
        default="all",
        help="Parser group to run",
    )
    args = parser.parse_args()

    total = 0
    runners = GROUPS[args.source]

    for runner in runners:
        try:
            total += runner()
        except Exception as e:
            logger.error(f"Runner {runner.__name__} failed: {e}", exc_info=True)
            continue

    logger.info(f"=== DONE. Total tenders: {total} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
