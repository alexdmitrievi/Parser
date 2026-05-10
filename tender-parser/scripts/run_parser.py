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
import json
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logging_config import configure_logging
from shared.db import insert_tenders, log_scrape_start, log_scrape_finish
from pipeline.normalizer import normalize_batch
from pipeline.tagger import tag_tenders_batch

configure_logging()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    force=False,
)
logger = logging.getLogger("parser")


def _process_and_save(tenders, source_name: str) -> int:
    """Нормализовать, протегировать и сохранить тендеры."""
    if not tenders:
        logger.warning(f"{source_name}: 0 tenders — possible scraper breakage!")
        return 0
    tenders = normalize_batch(tenders)
    tenders = tag_tenders_batch(tenders)
    count = insert_tenders(tenders)
    logger.info(f"{source_name}: saved {count} tenders")
    return count


def _run_with_log(runner_fn, group: str) -> int:
    """Запустить runner с записью в scrape_log."""
    name = runner_fn.__name__
    log_id = log_scrape_start(name, group)
    t0 = time.time()
    try:
        count = runner_fn()
        duration_ms = int((time.time() - t0) * 1000)
        log_scrape_finish(log_id, "success", tenders_found=count, tenders_inserted=count, duration_ms=duration_ms)
        return count
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        log_scrape_finish(log_id, "failed", error_message=str(e)[:500], duration_ms=duration_ms)
        logger.error(f"Runner {name} failed: {e}", exc_info=True)
        return 0


# ──────── ЕИС ────────

def run_eis_ftp() -> int:
    from scrapers.eis_ftp import EisFtpScraper
    logger.info("=== EIS FTP ===")
    scraper = EisFtpScraper()
    return _process_and_save(scraper.run(max_files_per_region=30), "EIS FTP")


def run_eis_api() -> int:
    from scrapers.eis_api import EisApiScraper
    from shared.constants import POPULAR_REGIONS
    logger.info("=== EIS API ===")
    scraper = EisApiScraper()
    total = 0

    # 1. Запросы с фильтром по популярным регионам (гарантирует точные результаты)
    queries_main = [
        "ремонт помещений", "строительные работы", "поставка оборудования",
        "мебель", "дизельное топливо", "медицинское оборудование",
        # ── Строительство и дороги ──
        "аренда спецтехники", "строительные материалы", "дорожные работы",
        "капитальный ремонт", "благоустройство", "реконструкция",
        # ── Рабочая сила ──
        "разнорабочие", "клининг",
        # ── Стройматериалы ──
        "поставка бетона", "поставка щебня", "металлопрокат поставка",
        "асфальтирование",
    ]
    for region in POPULAR_REGIONS:
        total += _process_and_save(
            scraper.run(queries=queries_main[:10], max_pages=3, region=region),
            f"EIS API [{region}]",
        )
        # Строительные запросы с ОКПД2-фильтром (точный поиск)
        total += _process_and_save(
            scraper.run(queries=queries_main[10:], max_pages=4, region=region,
                        okpd2="41.2;42.;43.;71.1"),
            f"EIS API constr [{region}]",
        )

    # 2. Широкие запросы без региона (для покрытия всех 85 регионов)
    queries_wide = [
        "IT услуги", "транспортные услуги", "мазут", "печное топливо",
        "продукты питания", "охранные услуги",
        # ── Строительные широкие ──
        "строительство дорог", "аренда экскаватора", "бетонные работы",
        "кровельные работы", "земляные работы", "фасадные работы",
    ]
    total += _process_and_save(
        scraper.run(queries=queries_wide, max_pages=3),
        "EIS API [all regions]",
    )

    # 3. 223-ФЗ запросы (отдельный фильтр по типу закона)
    for q in ["ремонт помещений", "поставка оборудования", "клининг",
              "строительные работы", "аренда спецтехники", "поставка стройматериалов"]:
        total += _process_and_save(
            scraper.run(queries=[q], max_pages=2, law_type="223-fz"),
            f"EIS API 223-ФЗ [{q}]",
        )
    return total


def run_eis_api_extra() -> int:
    """Дополнительные запросы ЕИС — менее частые ниши."""
    from scrapers.eis_api import EisApiScraper
    from shared.constants import POPULAR_REGIONS
    logger.info("=== EIS API (extra) ===")
    scraper = EisApiScraper()
    total = 0

    queries_extra = [
        "капитальный ремонт", "благоустройство", "реконструкция",
        "поставка продуктов", "поставка спецодежды",
        "ГСМ", "нефтепродукты", "уголь",
        "охранные услуги", "клининг", "проектные работы",
        "канцтовары", "спецтехника", "вывоз мусора",
        "страхование", "аудит",
        # ── Строительство и дороги ──
        "дорожные работы", "асфальтирование", "ямочный ремонт",
        "поставка бетона", "поставка щебня", "поставка арматуры",
        "металлопрокат", "кирпич поставка", "земляные работы",
        "свайные работы", "кровельные работы", "фасадные работы",
        "электромонтажные работы", "сантехнические работы",
        "вентиляция и кондиционирование", "монтаж металлоконструкций",
        # ── Рабочая сила и техника ──
        "грузчики", "подсобные рабочие", "разнорабочие",
        "аренда экскаватора", "аренда бульдозера", "аренда погрузчика",
        "аренда автокрана", "услуги спецтехники", "техника с экипажем",
        # ── Дорожные материалы ──
        "асфальтобетонная смесь", "битум дорожный", "тротуарная плитка",
        "бордюр дорожный", "дорожные знаки", "разметка дорожная",
    ]
    # С фильтром по популярным регионам
    for region in POPULAR_REGIONS:
        total += _process_and_save(
            scraper.run(queries=queries_extra[:12], max_pages=2, region=region),
            f"EIS API extra [{region}]",
        )
        # Строительные запросы с ОКПД2
        total += _process_and_save(
            scraper.run(queries=queries_extra[12:28], max_pages=3, region=region,
                        okpd2="41.2;42.;43.;71.1"),
            f"EIS API extra constr [{region}]",
        )
        # Техника и рабочая сила
        total += _process_and_save(
            scraper.run(queries=queries_extra[28:], max_pages=3, region=region),
            f"EIS API extra labor [{region}]",
        )

    # Широкие запросы без региона
    total += _process_and_save(
        scraper.run(queries=queries_extra, max_pages=2),
        "EIS API extra [all regions]",
    )
    return total


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
            queries=[
                "мебель поставка", "подряд строительство",
                "ремонт помещений", "изготовление мебели",
                "IT услуги", "медицинское оборудование",
                "продукты питания поставка", "охранные услуги",
                "клининг", "транспортные услуги",
                "спецодежда поставка", "канцтовары поставка",
                "проектные работы", "капитальный ремонт",
                "дизельное топливо", "строительные материалы",
            ],
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
    return _process_and_save(scraper.run(queries=[
        "ремонт", "поставка оборудования", "строительство",
        "IT услуги", "мебель", "уборка", "охрана",
        "продукты питания", "транспортные услуги",
        "аренда спецтехники", "строительные материалы",
        "дорожные работы", "бетон поставка", "щебень поставка",
        "металлопрокат", "кровельные работы", "земляные работы",
    ], max_pages=3), "Fabrikant PW")


def run_sberbank_ast_pw() -> int:
    from scrapers.sberbank_ast_pw import SberbankAstPlaywrightScraper
    logger.info("=== Sberbank-AST (Playwright) ===")
    scraper = SberbankAstPlaywrightScraper()
    return _process_and_save(scraper.run(), "Sberbank-AST PW")


# ──────── Аукционы (банкротство) ────────

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


# ──────── Corporate / Корпоративные площадки ────────

def run_gazprom() -> int:
    from scrapers.gazprom import GazpromScraper
    logger.info("=== Gazprom ===")
    scraper = GazpromScraper()
    return _process_and_save(scraper.run(), "Gazprom")


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


def run_mts() -> int:
    from scrapers.mts import MtsScraper
    logger.info("=== MTS ===")
    scraper = MtsScraper()
    return _process_and_save(scraper.run(), "MTS")


def run_sberb2b() -> int:
    from scrapers.sberb2b import SberB2bScraper
    logger.info("=== SberB2B ===")
    scraper = SberB2bScraper()
    return _process_and_save(scraper.run(), "SberB2B")


# ──────── Группы ────────

GROUPS = {
    "eis_ftp": [run_eis_ftp],
    "eis_api": [run_eis_api],
    "eis_api_extra": [run_eis_api_extra],
    "roseltorg": [run_roseltorg],
    "etp": [run_roseltorg, run_sberbank_ast, run_rts_tender, run_tektorg],
    "commercial": [run_b2b_center, run_rostender, run_tenderguru],
    "corporate": [run_gazprom, run_rosatom, run_rosneft, run_lukoil, run_nornickel, run_mts, run_sberb2b],
    "rostender": [run_rostender],
    "auctions": [run_lot_online, run_torgi_gov_pw],
    "auctions_rad": [run_lot_online],
    "auctions_torgi": [run_torgi_gov_pw],
    "playwright": [run_tektorg_pw, run_fabrikant_pw, run_sberbank_ast_pw],
    "all": [run_eis_ftp, run_eis_api, run_eis_api_extra, run_roseltorg,
            run_sberbank_ast, run_rts_tender, run_tektorg, run_b2b_center,
            run_tenderguru],
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
    group = args.source
    runners = GROUPS[group]

    for runner in runners:
        total += _run_with_log(runner, group)

    logger.info(f"=== DONE. Total tenders: {total} ===")

    # ── Generate hero.json for static hero stats on landing page ──
    try:
        generate_hero_json()
    except Exception as e:
        logger.error(f"Failed to generate hero.json: {e}")

    return 0


def generate_hero_json():
    """Write web/hero.json with live stats — used by landing page (no API call needed)."""
    from shared.db import get_db
    from datetime import datetime, timedelta, timezone

    db = get_db()
    total_res = db.table("tenders").select("id", count="exact").execute()
    total = total_res.count or 0

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_res = db.table("tenders").select("id", count="exact").gte("created_at", week_ago).execute()
    recent = recent_res.count or 0

    platforms_res = db.table("tenders").select("source_platform").limit(2000).execute()
    platforms = len(set(r.get("source_platform", "") for r in (platforms_res.data or []) if r.get("source_platform")))

    regions_res = db.table("tenders").select("customer_region").limit(2000).execute()
    regions = len(set((r.get("customer_region") or "").strip() for r in (regions_res.data or []) if (r.get("customer_region") or "").strip()))

    hero = {"total": total, "platforms": platforms, "regions": regions, "recent_7d": recent, "updated_at": datetime.now(timezone.utc).isoformat()}

    web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
    os.makedirs(web_dir, exist_ok=True)
    hero_path = os.path.join(web_dir, "hero.json")
    with open(hero_path, "w", encoding="utf-8") as f:
        json.dump(hero, f, ensure_ascii=False)
    logger.info(f"hero.json written: {hero['total']} tenders, {hero['platforms']} platforms, {hero['regions']} regions")


if __name__ == "__main__":
    sys.exit(main())
