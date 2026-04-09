"""Entry point для GitHub Actions: параллельный запуск парсеров.

Использование:
    python scripts/run_parser.py --source eis_ftp
    python scripts/run_parser.py --source eis_api
    python scripts/run_parser.py --source commercial
    python scripts/run_parser.py --source etp
    python scripts/run_parser.py --source corporate
    python scripts/run_parser.py --source all
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import insert_tenders
from pipeline.normalizer import normalize_batch
from pipeline.tagger import tag_tenders_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("parser")


# ─── Результат прогона одного скрапера ───────────────────────────────────────

@dataclass
class RunResult:
    name: str
    count: int = 0
    elapsed: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


# ─── Сохранение ──────────────────────────────────────────────────────────────

def _process_and_save(tenders, source_name: str) -> int:
    """Нормализовать, протегировать и сохранить тендеры."""
    if not tenders:
        logger.info(f"{source_name}: no tenders found")
        return 0
    tenders = normalize_batch(tenders)
    tenders = tag_tenders_batch(tenders)
    try:
        count = insert_tenders(tenders)
    except RuntimeError as e:
        logger.error(f"{source_name}: Supabase не настроен — {e}")
        return 0
    except Exception as e:
        logger.error(f"{source_name}: ошибка сохранения в БД — {e}")
        return 0
    logger.info(f"{source_name}: saved {count} tenders")
    return count


# ─── Скраперы: ЕИС ───────────────────────────────────────────────────────────

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
                "мебель", "IT услуги", "транспортные услуги",
                "мазут", "печное топливо", "дизельное топливо",
                "медицинское оборудование",
            ],
            max_pages=2,
        ),
        "EIS API",
    )


def run_eis_api_extra() -> int:
    """Дополнительные запросы ЕИС — менее частые ниши."""
    from scrapers.eis_api import EisApiScraper
    logger.info("=== EIS API (extra) ===")
    scraper = EisApiScraper()
    return _process_and_save(
        scraper.run(
            queries=[
                "капитальный ремонт", "благоустройство", "реконструкция",
                "поставка продуктов", "поставка спецодежды",
                "ГСМ", "нефтепродукты", "уголь",
                "охранные услуги", "клининг", "проектные работы",
                "канцтовары", "спецтехника", "вывоз мусора",
                "страхование", "аудит",
            ],
            max_pages=1,
        ),
        "EIS API extra",
    )


# ─── Скраперы: Федеральные ЭТП ──────────────────────────────────────────────

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


# ─── Скраперы: Коммерческие ──────────────────────────────────────────────────

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


# ─── Скраперы: Корпоративные площадки ───────────────────────────────────────

def run_sberb2b() -> int:
    from scrapers.sberb2b import SberB2BScraper
    logger.info("=== SberB2B ===")
    scraper = SberB2BScraper()
    return _process_and_save(scraper.run(), "SberB2B")


def run_rosatom() -> int:
    from scrapers.rosatom import RosatomScraper
    logger.info("=== Rosatom ===")
    scraper = RosatomScraper()
    return _process_and_save(scraper.run(), "Rosatom")


def run_rosneft() -> int:
    from scrapers.rosneft import RosneftScraper
    logger.info("=== Rosneft ===")
    scraper = RosneftScraper()
    return _process_and_save(scraper.run(), "Rosneft")


def run_gazprom() -> int:
    from scrapers.gazprom import GazpromScraper
    logger.info("=== Gazprom ===")
    scraper = GazpromScraper()
    return _process_and_save(scraper.run(), "Gazprom")


def run_lukoil() -> int:
    from scrapers.lukoil import LukoilScraper
    logger.info("=== Lukoil ===")
    scraper = LukoilScraper()
    return _process_and_save(scraper.run(), "Lukoil")


def run_nornickel() -> int:
    from scrapers.nornickel import NornickelScraper
    logger.info("=== Nornickel ===")
    scraper = NornickelScraper()
    return _process_and_save(scraper.run(), "Nornickel")


def run_mts_tenders() -> int:
    from scrapers.mts_tenders import MtsTendersScraper
    logger.info("=== MTS Tenders ===")
    scraper = MtsTendersScraper()
    return _process_and_save(scraper.run(), "MTS")


def run_rostelecom() -> int:
    from scrapers.rostelecom import RostelecomScraper
    logger.info("=== Rostelecom ===")
    scraper = RostelecomScraper()
    return _process_and_save(scraper.run(), "Rostelecom")


def run_x5group() -> int:
    from scrapers.x5group import X5GroupScraper
    logger.info("=== X5 Group ===")
    scraper = X5GroupScraper()
    return _process_and_save(scraper.run(), "X5Group")


def run_magnit() -> int:
    from scrapers.magnit import MagnitScraper
    logger.info("=== Magnit ===")
    scraper = MagnitScraper()
    return _process_and_save(scraper.run(), "Magnit")


# ─── Скраперы: Агрегаторы ────────────────────────────────────────────────────

def run_rostender() -> int:
    from scrapers.rostender import RostenderScraper
    logger.info("=== Rostender ===")
    scraper = RostenderScraper()
    return _process_and_save(scraper.run(), "Rostender")


# ─── Скраперы: Playwright ────────────────────────────────────────────────────

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


# ─── Скраперы: Аукционы ──────────────────────────────────────────────────────

def run_lot_online() -> int:
    from scrapers.lot_online import LotOnlineScraper
    logger.info("=== РАД (lot-online) ===")
    scraper = LotOnlineScraper()
    return _process_and_save(scraper.run(max_pages=5), "lot-online")


def run_torgi_gov_pw() -> int:
    from scrapers.torgi_gov_pw import TorgiGovPlaywrightScraper
    logger.info("=== Торги.гов.ру (Playwright) ===")
    scraper = TorgiGovPlaywrightScraper()
    return _process_and_save(scraper.run(max_pages=10), "Torgi.gov.ru")


# ─── Группы скраперов ────────────────────────────────────────────────────────

GROUPS: dict[str, list[Callable[[], int]]] = {
    "eis_ftp": [run_eis_ftp],
    "eis_api": [run_eis_api],
    "eis_api_extra": [run_eis_api_extra],
    "roseltorg": [run_roseltorg],
    "etp": [run_roseltorg, run_sberbank_ast, run_rts_tender, run_tektorg],
    "commercial": [run_b2b_center, run_rostender, run_tenderguru],
    # Корпоративные площадки (223-ФЗ / коммерческие)
    "corporate": [
        run_sberb2b, run_rosatom, run_rosneft, run_gazprom, run_lukoil,
        run_nornickel, run_mts_tenders, run_rostelecom, run_x5group, run_magnit,
    ],
    "corporate_energy": [run_rosatom, run_rosneft, run_gazprom, run_lukoil, run_nornickel],
    "corporate_telecom": [run_mts_tenders, run_rostelecom],
    "corporate_retail": [run_x5group, run_magnit],
    # Индивидуальные
    "sberb2b": [run_sberb2b],
    "rosatom": [run_rosatom],
    "rosneft": [run_rosneft],
    "gazprom": [run_gazprom],
    "lukoil": [run_lukoil],
    "nornickel": [run_nornickel],
    "mts_tenders": [run_mts_tenders],
    "rostelecom": [run_rostelecom],
    "x5group": [run_x5group],
    "magnit": [run_magnit],
    "rostender": [run_rostender],
    "auctions": [run_lot_online, run_torgi_gov_pw],
    "auctions_rad": [run_lot_online],
    "auctions_torgi": [run_torgi_gov_pw],
    "playwright": [run_tektorg_pw, run_fabrikant_pw, run_sberbank_ast_pw],
    "all": [
        run_eis_ftp, run_eis_api, run_roseltorg, run_sberbank_ast,
        run_rts_tender, run_tektorg, run_b2b_center, run_tenderguru,
        run_sberb2b, run_rosatom, run_rosneft, run_gazprom, run_lukoil,
        run_nornickel, run_mts_tenders, run_rostelecom, run_x5group, run_magnit,
    ],
}


# ─── Параллельный runner ─────────────────────────────────────────────────────

def _run_one(runner: Callable[[], int]) -> RunResult:
    """Запустить один скрапер, захватить результат и исключения."""
    name = runner.__name__
    t0 = time.time()
    try:
        count = runner()
        return RunResult(name=name, count=count, elapsed=time.time() - t0)
    except Exception as e:
        logger.error(f"Runner {name} failed: {e}", exc_info=True)
        return RunResult(name=name, elapsed=time.time() - t0, error=str(e))


def run_parallel(
    runners: list[Callable[[], int]], max_workers: int = 3
) -> list[RunResult]:
    """Запустить скраперы параллельно через ThreadPoolExecutor."""
    if len(runners) == 1:
        result = _run_one(runners[0])
        status = "✓" if result.ok else "✗"
        logger.info(f"{status} {result.name}: {result.count} тендеров ({result.elapsed:.1f}s)")
        return [result]

    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(runners))) as pool:
        future_to_name = {pool.submit(_run_one, r): r.__name__ for r in runners}
        for future in as_completed(future_to_name):
            result = future.result()
            results.append(result)
            status = "✓" if result.ok else "✗"
            msg = f"{result.count} тендеров" if result.ok else result.error
            logger.info(f"{status} {result.name}: {msg} ({result.elapsed:.1f}s)")
    return results


def _print_summary(results: list[RunResult], total_elapsed: float) -> None:
    total = sum(r.count for r in results)
    failed = [r for r in results if not r.ok]
    lines = ["", "─" * 60, "  ИТОГ ПАРСИНГА", "─" * 60]
    for r in sorted(results, key=lambda x: -x.count):
        status = "OK " if r.ok else "ERR"
        lines.append(f"  [{status}] {r.name:<30} {r.count:>5} тенд.  {r.elapsed:>6.1f}s")
    lines += [
        "─" * 60,
        f"  Итого: {total} тендеров за {total_elapsed:.1f}s",
    ]
    if failed:
        lines.append(f"  Ошибки ({len(failed)}): {', '.join(r.name for r in failed)}")
    lines.append("─" * 60)
    logger.info("\n".join(lines))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Tender Parser Runner")
    parser.add_argument(
        "--source",
        choices=list(GROUPS.keys()),
        default="all",
        help="Группа парсеров для запуска",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Число параллельных потоков (default: 3)",
    )
    args = parser.parse_args()

    runners = GROUPS[args.source]
    logger.info(
        f"Starting {len(runners)} scraper(s) for source='{args.source}' "
        f"workers={args.workers}"
    )

    t_start = time.time()
    results = run_parallel(runners, max_workers=args.workers)
    _print_summary(results, time.time() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
