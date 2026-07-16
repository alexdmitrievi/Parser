"""Протоколы подведения итогов из FTP ЕИС (этап 4).

Собираем протоколы по тем же регионам, оставляем только те, что относятся
к закупкам, прошедшим бизнес-фильтры (то есть попавшим в уведомления),
и копим в БД аналитику цен победителей. Уведомления не шлём.
"""

from __future__ import annotations

import logging
import os
import zipfile
from typing import Any, Optional
from xml.etree import ElementTree as ET

from engine.fetchers.ftp_fetcher import FtpFetcher
from engine.sources.tenders.eis_ftp import (
    DEFAULT_REGIONS,
    PROTOCOL_LAYOUT_44,
    PROTOCOL_LAYOUT_223,
    EisFtpLayout,
    EisRegion,
    _first,
    _first_text,
    _iter_named,
    _local,
    _region_match,
    _to_dt,
    _to_float,
)

logger = logging.getLogger("monitor.protocols")


# ─────────────────────── Парсинг протоколов ───────────────────────

def parse_44fz_protocol(xml_content: str) -> Optional[dict[str, Any]]:
    """Извлечь итоги из fcsProtocol* XML (44-ФЗ)."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    doc = root
    if _local(root.tag) in ("export", "fcsExport") and len(root):
        doc = root[0]
    if "rotocol" not in _local(doc.tag):
        return None

    registry_number = _first_text(doc, ("purchaseNumber",))
    if not registry_number:
        return None

    protocol_date = _to_dt(_first_text(doc, ("publishDTInEIS", "docPublishDate",
                                             "protocolDate", "signDate")))

    applications = list(_iter_named(doc, ("application", "appInfo")))
    participants_count = len(applications) or None

    winner_name = winner_inn = None
    winner_price = None

    def _app_price(app: ET.Element) -> Optional[float]:
        return _to_float(_first_text(app, ("price", "appPrice", "contractPrice",
                                           "priceOffer")))

    winner_app = None
    for app in applications:
        rating = _first_text(app, ("appRating", "rating"))
        if rating and rating.strip() == "1":
            winner_app = app
            break
    if winner_app is None and applications:
        priced = [(a, _app_price(a)) for a in applications]
        priced = [(a, p) for a, p in priced if p is not None]
        if priced:
            winner_app = min(priced, key=lambda ap: ap[1])[0]

    if winner_app is not None:
        winner_name = _first_text(winner_app, ("participantName", "organizationName",
                                               "fullName", "name"))
        winner_inn = _first_text(winner_app, ("inn", "INN"))
        winner_price = _app_price(winner_app)

    return {
        "registry_number": registry_number,
        "law_type": "44-fz",
        "protocol_date": protocol_date,
        "participants_count": participants_count,
        "winner_name": winner_name,
        "winner_inn": winner_inn,
        "winner_price": winner_price,
    }


def parse_223fz_protocol(xml_content: str) -> Optional[dict[str, Any]]:
    """Извлечь итоги из purchaseProtocol XML (223-ФЗ), best-effort."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    data = _first(root, ("purchaseProtocolData", "protocolData")) or root
    registry_number = _first_text(data, ("purchaseNoticeNumber", "registrationNumber"))
    if not registry_number:
        return None

    protocol_date = _to_dt(_first_text(data, ("publicationDateTime", "approveDate",
                                              "createDateTime")))

    applications = list(_iter_named(data, ("application", "applicationInfo",
                                           "supplierInfo")))
    participants_count = len(applications) or None

    winner_name = winner_inn = None
    winner_price = None
    winner = _first(data, ("winnerInfo", "winner"))
    if winner is None:
        for app in applications:
            if (_first_text(app, ("winnerIndication", "isWinner")) or "").lower() in ("w", "true", "1"):
                winner = app
                break
    if winner is not None:
        winner_name = _first_text(winner, ("name", "fullName", "organizationName"))
        winner_inn = _first_text(winner, ("inn", "INN"))
        winner_price = _to_float(_first_text(winner, ("price", "sum", "contractSum")))

    return {
        "registry_number": registry_number,
        "law_type": "223-fz",
        "protocol_date": protocol_date,
        "participants_count": participants_count,
        "winner_name": winner_name,
        "winner_inn": winner_inn,
        "winner_price": winner_price,
    }


# ─────────────────────── Сбор с FTP ───────────────────────

class ProtocolCollector:
    """Скачивает архивы протоколов по регионам и пишет итоги в БД."""

    def __init__(
        self,
        repo,
        regions: list[EisRegion] | None = None,
        tmp_dir: str | None = None,
        max_archives: int | None = None,
    ):
        self._repo = repo
        self._regions = regions or DEFAULT_REGIONS
        self._tmp_dir = tmp_dir
        self._max_archives = max_archives or int(
            os.environ.get("EIS_FTP_MAX_ARCHIVES", "300")
        )

    def _discover(self, ftp: FtpFetcher, layout: EisFtpLayout,
                  region_by_path: dict[str, str]) -> list[str]:
        entries = ftp.list_dirs(layout.base_dir)
        archives: list[str] = []
        for region in self._regions:
            region_dir = _region_match(entries, region)
            if not region_dir:
                continue
            for subdir in layout.subdir_candidates:
                path = f"{layout.base_dir}/{region_dir}/{subdir}"
                for fname in ftp.list_files(path, pattern="*.xml.zip"):
                    full = f"{path}/{fname.rsplit('/', 1)[-1]}"
                    archives.append(full)
                    region_by_path[full] = region.display_name
        archives = sorted(set(archives))
        archives = self._repo.filter_new_archives(archives)
        return archives[: self._max_archives]

    def collect(self) -> dict[str, int]:
        """Один проход сбора протоколов. Возвращает статистику."""
        stats = {"archives": 0, "parsed": 0, "stored": 0}
        filtered_regs = self._repo.fetch_filtered_registry_numbers()
        if not filtered_regs:
            logger.info("No filtered tenders yet — skipping protocol collection")
            return stats

        host = os.environ.get("EIS_FTP_HOST", "ftp.zakupki.gov.ru")
        user = os.environ.get("EIS_FTP_USER", "free")
        passwd = os.environ.get("EIS_FTP_PASS", "free")

        for layout, parse_fn, source_id in (
            (PROTOCOL_LAYOUT_44, parse_44fz_protocol, "eis_protocols_44"),
            (PROTOCOL_LAYOUT_223, parse_223fz_protocol, "eis_protocols_223"),
        ):
            region_by_path: dict[str, str] = {}
            try:
                with FtpFetcher() as ftp:
                    ftp.connect(host, user=user, passwd=passwd)
                    archives = self._discover(ftp, layout, region_by_path)
                    logger.info(f"[{source_id}] {len(archives)} new protocol archives")

                    for archive in archives:
                        try:
                            stored = self._process_archive(
                                ftp, archive, parse_fn,
                                region_by_path.get(archive), filtered_regs,
                            )
                            stats["archives"] += 1
                            stats["stored"] += stored
                            self._repo.mark_archives_processed([archive], source_id)
                        except Exception as e:
                            logger.warning(f"[{source_id}] Archive {archive} failed: {e}")
            except Exception as e:
                logger.error(f"[{source_id}] Protocol collection failed: {e}")

        logger.info(f"Protocols: {stats}")
        return stats

    def _process_archive(self, ftp: FtpFetcher, archive: str, parse_fn,
                         region: Optional[str], filtered_regs: set[str]) -> int:
        stored = 0
        local_path = ftp.download_to_file(archive, dest_dir=self._tmp_dir)
        try:
            with zipfile.ZipFile(local_path) as zf:
                for name in zf.namelist():
                    if not name.endswith(".xml"):
                        continue
                    xml_bytes = zf.read(name)
                    try:
                        xml_content = xml_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        xml_content = xml_bytes.decode("cp1251", errors="replace")

                    protocol = parse_fn(xml_content)
                    if not protocol:
                        continue
                    if protocol["registry_number"] not in filtered_regs:
                        continue

                    self._enrich_with_nmck(protocol)
                    protocol["region"] = region
                    protocol["raw_data"] = {"archive": archive, "inner_file": name}
                    self._repo.upsert_protocol(protocol)
                    stored += 1
        except zipfile.BadZipFile:
            logger.warning(f"Bad protocol ZIP: {archive}")
        finally:
            try:
                os.unlink(local_path)
            except OSError:
                pass
        return stored

    def _enrich_with_nmck(self, protocol: dict[str, Any]) -> None:
        """Подтянуть НМЦК из нашей БД и посчитать снижение в %."""
        existing = self._repo.fetch_existing_by_registry([protocol["registry_number"]])
        tender = existing.get(protocol["registry_number"])
        if not tender:
            return
        nmck = tender.get("nmck")
        protocol["nmck"] = float(nmck) if nmck is not None else None
        price = protocol.get("winner_price")
        if protocol["nmck"] and price is not None and protocol["nmck"] > 0:
            protocol["reduction_pct"] = round(
                (protocol["nmck"] - float(price)) / protocol["nmck"] * 100, 2
            )
