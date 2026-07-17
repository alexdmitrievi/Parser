"""EIS FTP source: official XML dumps from ftp.zakupki.gov.ru.

Primary production source for the monitor. Downloads regional archives of
44-FZ and 223-FZ notices, parses them into ParsedRecords, and tracks
processed archives in PostgreSQL so each cycle fetches only what is new.
Archives are downloaded to a temp dir and deleted right after parsing.

FTP layout (verified with scripts/eis_ftp_probe.py on the target VPS):
    44-FZ: /fcs_regions/<Region_dir>/notifications/{currMonth,prevMonth}/*.xml.zip
    223-FZ: /out/published/<Region_dir>/purchase_notice*/... (*.xml.zip)

Region directory names on the FTP are transliterated inconsistently
(e.g. "Omskaja_obl" vs "Omskaya_obl"), so regions are located by
case-insensitive substring match instead of hardcoded names.

Credentials: anonymous access; historically login "free"/"free" is required
for the 223-FZ subtree. Override via EIS_FTP_USER / EIS_FTP_PASS.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from xml.etree import ElementTree as ET

from engine.types import (
    SourceConfig, SourceCategory, FetchMethod, FetchResult, ParsedRecord,
    RateLimitConfig,
)
from engine.sources.base import BaseSourceAdapter
from engine.fetchers.ftp_fetcher import FtpFetcher, iter_local_zip_xml
from engine.config.registry import get_registry
from engine.observability.logger import get_logger

logger = get_logger("source.eis_ftp")


# ─────────────────────── Namespace-agnostic XML helpers ───────────────────────

def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _iter_named(root: ET.Element, names: Iterable[str]) -> Iterable[ET.Element]:
    nameset = set(names)
    for el in root.iter():
        if _local(el.tag) in nameset:
            yield el


def _first(root: ET.Element, names: Iterable[str]) -> Optional[ET.Element]:
    for el in _iter_named(root, names):
        return el
    return None


def _first_text(root: ET.Element, names: Iterable[str]) -> Optional[str]:
    for el in _iter_named(root, names):
        if el.text and el.text.strip():
            return el.text.strip()
    return None


def _child_text(el: ET.Element, names: Iterable[str]) -> Optional[str]:
    nameset = set(names)
    for child in el:
        if _local(child.tag) in nameset and child.text and child.text.strip():
            return child.text.strip()
    return None


def _to_float(text: str | None) -> Optional[float]:
    if not text:
        return None
    try:
        val = float(text.replace(",", ".").replace(" ", ""))
        return val if val > 0 else None
    except ValueError:
        return None


_MSK = timezone(timedelta(hours=3))


def _to_dt(text: str | None) -> Optional[datetime]:
    """Parse EIS datetime. Naive values are treated as Moscow time (+03:00) —
    выгрузки ЕИС публикуют даты по МСК; иначе naive-значение легло бы в
    TIMESTAMPTZ как UTC и дедлайн в карточке уехал бы на 3 часа."""
    if not text:
        return None
    t = text.strip().replace("Z", "+00:00")
    for candidate in (t, t[:19]):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_MSK)
            return dt
        except ValueError:
            continue
    return None


# ─────────────────────── 44-FZ notification parsing ───────────────────────

# Способ закупки по типу корневого документа (когда placingWay отсутствует)
_44_METHOD_BY_DOCTYPE = {
    "EF": "Электронный аукцион",
    "OK": "Открытый конкурс",
    "ZK": "Запрос котировок",
    "ZP": "Запрос предложений",
    "EP": "Закупка у единственного поставщика",
    "ISM": "Закрытая закупка",
}

_44_INNER_SKIP = ("Cancel", "cancel", "Clarification", "LotChange", "Organization")


def _doc_type_suffix(root_tag: str) -> str:
    m = re.search(r"[Nn]otification([A-Z]+\d*)$", root_tag)
    return m.group(1) if m else ""


def parse_44fz_notification(xml_content: str) -> Optional[dict[str, Any]]:
    """Parse a 44-FZ fcsNotification* XML into a plain field dict."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    # export-обёртка: настоящий документ — первый ребёнок
    doc = root
    if _local(root.tag) in ("export", "fcsExport") and len(root):
        doc = root[0]

    registry_number = _first_text(doc, ("purchaseNumber",))
    if not registry_number:
        return None

    title = _first_text(doc, ("purchaseObjectInfo",))
    if not title:
        return None

    # Заказчик: fullName/ИНН внутри блока ответственной организации
    customer_name = None
    customer_inn = None
    resp = _first(doc, ("purchaseResponsibleInfo", "purchaseResponsible",
                        "responsibleOrgInfo", "responsibleOrg"))
    if resp is not None:
        customer_name = _first_text(resp, ("fullName",))
        customer_inn = _first_text(resp, ("INN", "inn"))
    if not customer_name:
        customer_name = _first_text(doc, ("fullName",))
    if not customer_inn:
        customer_inn = _first_text(doc, ("INN", "inn"))

    nmck = _to_float(_first_text(doc, ("maxPrice",)))

    # Окончание подачи заявок — внутри collectingInfo/collecting
    deadline = None
    collecting = _first(doc, ("collectingInfo", "collecting"))
    if collecting is not None:
        deadline = _to_dt(_first_text(collecting, ("endDT", "endDate")))
    if deadline is None:
        deadline = _to_dt(_first_text(doc, ("applEndDate", "submissionCloseDateTime")))

    publish_date = _to_dt(_first_text(doc, ("publishDTInEIS", "docPublishDate", "publishDate")))

    # Обеспечение заявки / контракта
    application_guarantee = None
    app_g = _first(doc, ("applicationGuarantee", "applicationGuaranteeInfo"))
    if app_g is not None:
        application_guarantee = _to_float(_first_text(app_g, ("amount",)))

    contract_guarantee = None
    con_g = _first(doc, ("contractGuarantee", "contractGuaranteeInfo"))
    if con_g is not None:
        contract_guarantee = _to_float(_first_text(con_g, ("amount",)))

    # Способ закупки
    purchase_method = None
    placing = _first(doc, ("placingWay", "placingWayInfo"))
    if placing is not None:
        purchase_method = _child_text(placing, ("name",)) or _first_text(placing, ("name",))
    if not purchase_method:
        purchase_method = _44_METHOD_BY_DOCTYPE.get(_doc_type_suffix(_local(doc.tag)))

    # ОКПД2-коды позиций
    okpd2: list[str] = []
    for el in _iter_named(doc, ("OKPD2", "okpd2", "OKPD2Info")):
        code = _child_text(el, ("code", "OKPDCode")) or _first_text(el, ("code", "OKPDCode"))
        if code and code not in okpd2:
            okpd2.append(code)

    # Ссылка на карточку в ЕИС: элемент href в новых схемах
    url = None
    for el in _iter_named(doc, ("href",)):
        if el.text and el.text.strip().startswith("http"):
            url = el.text.strip()
            break
    if not url:
        # Путь карточки зависит от способа закупки (ea44/ok504/…), угадать его
        # нельзя — надёжнее универсальный поиск по номеру извещения.
        url = (
            "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"
            f"?searchString={registry_number}"
        )

    return {
        "registry_number": registry_number,
        "title": title,
        "customer_name": customer_name,
        "customer_inn": customer_inn,
        "nmck": nmck,
        "submission_deadline": deadline,
        "publish_date": publish_date,
        "application_guarantee": application_guarantee,
        "contract_guarantee": contract_guarantee,
        "purchase_method": purchase_method,
        "okpd2_codes": okpd2,
        "original_url": url,
        "law_type": "44-fz",
    }


# ─────────────────────── 223-FZ purchaseNotice parsing ───────────────────────

def parse_223fz_notice(xml_content: str) -> Optional[dict[str, Any]]:
    """Parse a 223-FZ purchaseNotice XML into a plain field dict."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    data = _first(root, ("purchaseNoticeData", "purchaseNoticeInfoData",
                         "commonDataInfo")) or root

    registry_number = _first_text(data, ("registrationNumber",))
    if not registry_number:
        return None

    # Наименование закупки: прямой ребёнок name у data-блока,
    # иначе purchaseObjectInfo / первый name.
    title = (_child_text(data, ("name",))
             or _first_text(data, ("purchaseObjectInfo",)))
    if not title:
        purchase_info = _first(data, ("purchaseInfo",))
        if purchase_info is not None:
            title = _child_text(purchase_info, ("name", "purchaseObjectInfo"))
    if not title:
        return None

    customer_name = None
    customer_inn = None
    customer = _first(data, ("customer", "customerInfo", "placer", "placerInfo"))
    if customer is not None:
        customer_name = _first_text(customer, ("fullName", "name"))
        customer_inn = _first_text(customer, ("inn", "INN"))

    nmck = _to_float(_first_text(data, ("initialSum", "lotMaximumPrice", "maxPrice", "sum")))

    deadline = _to_dt(_first_text(data, ("submissionCloseDateTime", "submissionCloseDate",
                                         "endDate", "endDT")))
    publish_date = _to_dt(_first_text(data, ("publicationDateTime", "publishDate",
                                             "createDateTime")))

    purchase_method = _first_text(data, ("purchaseMethodName", "purchaseCodeName"))

    okpd2: list[str] = []
    for el in _iter_named(data, ("okpd2", "OKPD2")):
        code = _child_text(el, ("code",)) or _first_text(el, ("code",))
        if code and code not in okpd2:
            okpd2.append(code)

    url = _first_text(data, ("urlEIS", "urlOOS", "url"))
    if not url or not url.startswith("http"):
        url = (
            "https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html"
            f"?regNumber={registry_number}"
        )

    return {
        "registry_number": registry_number,
        "title": title,
        "customer_name": customer_name,
        "customer_inn": customer_inn,
        "nmck": nmck,
        "submission_deadline": deadline,
        "publish_date": publish_date,
        "application_guarantee": None,
        "contract_guarantee": None,
        "purchase_method": purchase_method,
        "okpd2_codes": okpd2,
        "original_url": url,
        "law_type": "223-fz",
    }


# ─────────────────────── Region / dir discovery ───────────────────────

@dataclass
class EisRegion:
    """A monitored region: FTP dir match pattern + display name."""
    match: str  # подстрока для поиска каталога региона (lowercase)
    display_name: str  # человекочитаемое имя для customer_region


DEFAULT_REGIONS = [
    EisRegion(match="omsk", display_name="Омская область"),
    EisRegion(match="novosibirsk", display_name="Новосибирская область"),
]


@dataclass
class EisFtpLayout:
    """FTP layout for one law type."""
    law_type: str
    base_dir: str
    subdir_candidates: list[str] = field(default_factory=list)


LAYOUT_44 = EisFtpLayout(
    law_type="44-fz",
    base_dir="/fcs_regions",
    subdir_candidates=["notifications/currMonth", "notifications/prevMonth"],
)

LAYOUT_223 = EisFtpLayout(
    law_type="223-fz",
    base_dir="/out/published",
    subdir_candidates=[
        "purchase_notice", "purchaseNotice",
        "purchase_notice/daily", "purchaseNotice/daily",
    ],
)

PROTOCOL_LAYOUT_44 = EisFtpLayout(
    law_type="44-fz",
    base_dir="/fcs_regions",
    subdir_candidates=["protocols/currMonth", "protocols/prevMonth"],
)

PROTOCOL_LAYOUT_223 = EisFtpLayout(
    law_type="223-fz",
    base_dir="/out/published",
    subdir_candidates=["purchase_protocol", "purchaseProtocol"],
)


def _region_match(entries: list[str], region: EisRegion) -> Optional[str]:
    """Find the FTP dir entry matching a region, tolerant to transliteration.

    Сравнение по началу токенов имени каталога, а не по подстроке:
    "omsk" должен находить "Omskaja_obl"/"Omskaya_obl", но НЕ "Tomskaja_obl".
    """
    display_first = region.display_name.lower().split()[0]
    for entry in entries:
        name = entry.rstrip("/").rsplit("/", 1)[-1]
        tokens = re.split(r"[_\-\s.]+", name.lower())
        for token in tokens:
            if token.startswith(region.match) or token.startswith(display_first):
                return name
    return None


# ─────────────────────── Source adapter ───────────────────────

class EisFtpSourceAdapter(BaseSourceAdapter):
    """Engine adapter for EIS FTP dumps (one instance per law type).

    Flow (driven by PipelineOrchestrator):
        discover()      → list new *.xml.zip archives (incremental via repo)
        fetch_page()    → download archive to temp file, return its local path
        parse_listing() → extract XMLs, parse notices, delete the temp file
    """

    # Orchestrator hints: FTP is a feed, not a paginated search
    stop_on_empty_page = False
    empty_discovery_ok = True
    empty_parse_ok = True

    def __init__(
        self,
        config: SourceConfig,
        layout: EisFtpLayout,
        repo: Any = None,
        regions: list[EisRegion] | None = None,
        max_archives: int | None = None,
        tmp_dir: str | None = None,
    ):
        super().__init__(config)
        self._layout = layout
        self._repo = repo  # PostgresTenderRepository | None (None → без инкрементальности)
        self._regions = regions or DEFAULT_REGIONS
        self._max_archives = max_archives or int(os.environ.get("EIS_FTP_MAX_ARCHIVES", "300"))
        self._tmp_dir = tmp_dir
        self._ftp: FtpFetcher | None = None
        self._region_by_path: dict[str, str] = {}
        # Архивы, успешно разобранные в этом прогоне; run_cycle помечает их
        # обработанными в БД только после успешной записи тендеров.
        self.parsed_archives: list[str] = []

    # --------------- FTP session ---------------

    def _get_ftp(self) -> FtpFetcher:
        if self._ftp is None or not self._ftp.connected:
            host = os.environ.get("EIS_FTP_HOST", "ftp.zakupki.gov.ru")
            user = os.environ.get("EIS_FTP_USER", "free")
            passwd = os.environ.get("EIS_FTP_PASS", "free")
            self._ftp = FtpFetcher(self.config)
            self._ftp.connect(host, user=user, passwd=passwd)
        return self._ftp

    # --------------- Discovery ---------------

    def discover(self) -> list[str]:
        ftp = self._get_ftp()
        base = self._layout.base_dir
        entries = ftp.list_dirs(base)
        if not entries:
            raise RuntimeError(f"FTP dir {base} is empty or unreadable")

        archives: list[str] = []
        matched_regions = 0
        for region in self._regions:
            region_dir = _region_match(entries, region)
            if not region_dir:
                logger.warning(
                    f"[{self.source_id}] Region '{region.display_name}' not found under {base}"
                )
                continue
            matched_regions += 1

            for subdir in self._layout.subdir_candidates:
                path = f"{base}/{region_dir}/{subdir}"
                files = ftp.list_files(path, pattern="*.xml.zip")
                if not files:
                    continue
                for fname in files:
                    full = f"{path}/{fname.rsplit('/', 1)[-1]}"
                    archives.append(full)
                    self._region_by_path[full] = region.display_name

        if matched_regions == 0:
            raise RuntimeError(
                f"None of the configured regions found under {base} — "
                "FTP layout changed? Run scripts/eis_ftp_probe.py"
            )

        archives = sorted(set(archives))
        if self._repo is not None:
            archives = self._repo.filter_new_archives(archives)
        if len(archives) > self._max_archives:
            logger.info(
                f"[{self.source_id}] {len(archives)} new archives, "
                f"capping at {self._max_archives} for this cycle"
            )
            archives = archives[: self._max_archives]

        logger.info(f"[{self.source_id}] {len(archives)} new archives to process")
        return archives

    # --------------- Fetch ---------------

    def fetch_page(self, url: str) -> FetchResult:
        ftp = self._get_ftp()
        local_path = ftp.download_to_file(url, dest_dir=self._tmp_dir)
        return FetchResult(
            url=url,
            content=local_path,
            content_type="application/zip+local-path",
            fetch_method=FetchMethod.FTP,
        )

    # --------------- Parse ---------------

    def parse_listing(self, result: FetchResult) -> list[ParsedRecord]:
        local_path = str(result.content)
        region = self._region_by_path.get(result.url)
        records: list[ParsedRecord] = []

        for name, xml_content in iter_local_zip_xml(local_path, _44_INNER_SKIP):
            fields = self._parse_document(xml_content)
            if not fields:
                continue
            records.append(ParsedRecord(
                source_id=self.config.source_id,
                category=SourceCategory.TENDERS,
                customer_region=region,
                raw_data={"archive": result.url, "inner_file": name},
                **fields,
            ))

        self.parsed_archives.append(result.url)
        return records

    def _parse_document(self, xml_content: str) -> Optional[dict[str, Any]]:
        if self._layout.law_type == "44-fz":
            return parse_44fz_notification(xml_content)
        return parse_223fz_notice(xml_content)

    # --------------- Lifecycle ---------------

    def commit_processed(self) -> None:
        """Mark successfully parsed archives as processed (call after persist)."""
        if self._repo is not None and self.parsed_archives:
            self._repo.mark_archives_processed(self.parsed_archives, self.source_id)
            self.parsed_archives = []

    def __exit__(self, *exc):
        if self._ftp:
            self._ftp.close()
            self._ftp = None
        super().__exit__(*exc)


# ─────────────────────── Configs & registration ───────────────────────

EIS_FTP_44_CONFIG = SourceConfig(
    source_id="eis_ftp_44",
    platform_name="eis",
    category=SourceCategory.TENDERS,
    base_url="ftp://ftp.zakupki.gov.ru",
    fetch_method=FetchMethod.FTP,
    rate_limit=RateLimitConfig(min_delay=0.3, max_delay=1.0),
    law_type_default="44-fz",
)

EIS_FTP_223_CONFIG = SourceConfig(
    source_id="eis_ftp_223",
    platform_name="eis",
    category=SourceCategory.TENDERS,
    base_url="ftp://ftp.zakupki.gov.ru",
    fetch_method=FetchMethod.FTP,
    rate_limit=RateLimitConfig(min_delay=0.3, max_delay=1.0),
    law_type_default="223-fz",
)


def register_eis_ftp() -> None:
    registry = get_registry()
    registry.register(EIS_FTP_44_CONFIG, EisFtpSourceAdapter)
    registry.register(EIS_FTP_223_CONFIG, EisFtpSourceAdapter)


def make_eis_ftp_adapters(repo: Any, tmp_dir: str | None = None) -> list[EisFtpSourceAdapter]:
    """Build both law-type adapters wired to the given repository."""
    return [
        EisFtpSourceAdapter(EIS_FTP_44_CONFIG, LAYOUT_44, repo=repo, tmp_dir=tmp_dir),
        EisFtpSourceAdapter(EIS_FTP_223_CONFIG, LAYOUT_223, repo=repo, tmp_dir=tmp_dir),
    ]
