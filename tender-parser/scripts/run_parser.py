"""Entry point для GitHub Actions: запуск парсеров.

Использование:
    python scripts/run_parser.py --source eis_ftp
    python scripts/run_parser.py --source tenderguru
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


def run_eis_ftp() -> int:
    """Запустить парсер FTP ЕИС."""
    from scrapers.eis_ftp import EisFtpScraper

    logger.info("=== Starting EIS FTP parser ===")
    scraper = EisFtpScraper()
    tenders = scraper.run(max_files_per_region=30)

    if tenders:
        tenders = normalize_batch(tenders)
        tenders = tag_tenders_batch(tenders)
        count = insert_tenders(tenders)
        logger.info(f"EIS FTP: inserted/updated {count} tenders")
        return count
    return 0


def run_tenderguru() -> int:
    """Запустить парсер TenderGuru."""
    from scrapers.tenderguru import TenderGuruScraper

    logger.info("=== Starting TenderGuru parser ===")
    scraper = TenderGuruScraper()
    tenders = scraper.run(
        queries=["мебель поставка", "подряд строительство", "ремонт помещений", "изготовление мебели"],
        max_pages=3,
    )

    if tenders:
        tenders = normalize_batch(tenders)
        tenders = tag_tenders_batch(tenders)
        count = insert_tenders(tenders)
        logger.info(f"TenderGuru: inserted/updated {count} tenders")
        return count
    return 0


def main():
    parser = argparse.ArgumentParser(description="Tender Parser Runner")
    parser.add_argument(
        "--source",
        choices=["eis_ftp", "tenderguru", "all"],
        default="all",
        help="Which parser to run",
    )
    args = parser.parse_args()

    total = 0

    if args.source in ("eis_ftp", "all"):
        total += run_eis_ftp()

    if args.source in ("tenderguru", "all"):
        total += run_tenderguru()

    logger.info(f"=== Done. Total tenders processed: {total} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
