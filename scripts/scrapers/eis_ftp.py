"""FTP ЕИС: XML уведомлений 44-ФЗ и 223-ФЗ."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from ftplib import FTP, error_perm
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

FTP_HOST = "ftp.zakupki.gov.ru"


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class EisFtpScraper:
    """Скачивание и разбор XML с FTP ЕИС."""

    source_platform = "eis_ftp"
    law_type = "44-fz"

    def __init__(self, region: str = "77") -> None:
        self.region = region

    def _parse_xml_44(self, root: ET.Element) -> dict[str, Any] | None:
        def find_text(path_candidates: list[str]) -> str | None:
            for el in root.iter():
                if _local(el.tag) in path_candidates and (el.text or "").strip():
                    return el.text.strip()
            return None

        purchase_number = find_text(["purchaseNumber", "purchase_number"])
        name = find_text(["name", "objectInfo", "purchaseObjectInfo"])
        if not name:
            for el in root.iter():
                if _local(el.tag) == "name" and (el.text or "").strip():
                    name = el.text.strip()
                    break
        customer = None
        for el in root.iter():
            if _local(el.tag) in ("fullName", "organizationName", "customerName"):
                if el.text and len(el.text) > 3:
                    customer = el.text.strip()
                    break
        max_price = find_text(["maxPrice", "maxContractPrice", "price"])
        close = find_text(["submissionCloseDateTime", "collectingEndDate", "endDate"])
        notif_date = find_text(["notificationDate", "publishDate", "docPublishDate"])
        if not purchase_number and not name:
            return None
        return {
            "registry_number": purchase_number or (name or "")[:40],
            "title": name or purchase_number or "Без названия",
            "customer_name": customer,
            "nmck": _num(max_price),
            "submission_deadline_raw": close,
            "notification_date_raw": notif_date,
            "law_type": "44-fz",
            "source_platform": self.source_platform,
            "external_url": f"https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber={purchase_number or ''}",
        }

    def _parse_xml_223(self, root: ET.Element) -> dict[str, Any] | None:
        """Схема 223-ФЗ: purchaseNumber, name, customer/mainInfo/fullName, lot/maxPrice, даты."""

        def find_first(tags: list[str]) -> str | None:
            for t in tags:
                for el in root.iter():
                    if _local(el.tag) == t and (el.text or "").strip():
                        return el.text.strip()
            return None

        def find_nested_customer() -> str | None:
            for el in root.iter():
                if _local(el.tag) == "customer":
                    for ch in el.iter():
                        if _local(ch.tag) == "mainInfo":
                            for g in ch.iter():
                                if _local(g.tag) == "fullName" and (g.text or "").strip():
                                    return g.text.strip()
            return None

        purchase_number = find_first(["purchaseNumber", "registrationNumber"])
        name = find_first(["name", "purchaseObjectInfo", "objectName"])
        customer = find_nested_customer() or find_first(
            ["fullName", "organizationName", "customerFullName"]
        )
        max_price = None
        for el in root.iter():
            if _local(el.tag) == "lot":
                for child in el.iter():
                    if _local(child.tag) == "maxPrice" and (child.text or "").strip():
                        max_price = child.text.strip()
                        break
        max_price = max_price or find_first(["maxPrice", "initialContractPrice"])
        close = find_first(["submissionCloseDateTime", "submissionCloseDate", "endDate"])
        notif_date = find_first(["notificationDate", "publishDate", "docPublishDate"])

        if not purchase_number and not name:
            return None
        pn = purchase_number or re.sub(r"\W+", "_", (name or "")[:50])
        return {
            "registry_number": pn,
            "title": name or pn,
            "customer_name": customer,
            "nmck": _num(max_price),
            "submission_deadline_raw": close,
            "notification_date_raw": notif_date,
            "law_type": "223-fz",
            "source_platform": self.source_platform,
            "external_url": (
                f"https://zakupki.gov.ru/epz/order/notice/ea223/view/common-info.html?"
                f"regNumber={purchase_number or ''}"
            ),
        }

    def _parse_file(self, data: bytes, path_hint: str) -> dict[str, Any] | None:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            logger.debug("xml parse error %s: %s", path_hint, e)
            return None
        if "223" in path_hint or "purchaseNotifications223" in path_hint:
            return self._parse_xml_223(root)
        return self._parse_xml_44(root)

    def run(self) -> list[dict[str, Any]]:
        """XML из FTP: уведомления 44-ФЗ (каталог по региону)."""
        return self._fetch_dir(f"/fcs_regions/{self.region}/notifications/")

    def run_223(self) -> list[dict[str, Any]]:
        """Каталог 223-ФЗ: /fcs_regions/{region}/purchaseNotifications223/."""
        return self._fetch_dir(f"/fcs_regions/{self.region}/purchaseNotifications223/")

    def _fetch_dir(self, remote_dir: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        ftp: FTP | None = None
        try:
            ftp = FTP(FTP_HOST, timeout=90)
            ftp.login()
            ftp.cwd(remote_dir)
            names: list[str] = []
            ftp.retrlines("NLST", names.append)
        except (OSError, error_perm) as e:
            logger.warning("FTP list failed %s: %s", remote_dir, e)
            return []
        assert ftp is not None
        for name in names:
            if not name.lower().endswith(".xml"):
                continue
            buf = BytesIO()
            try:
                ftp.retrbinary(f"RETR {name}", buf.write)
            except error_perm:
                continue
            data = buf.getvalue()
            parsed = self._parse_file(data, remote_dir + "/" + name)
            if parsed:
                out.append(parsed)
        try:
            ftp.quit()
        except Exception:
            pass
        return out


def _num(s: str | None) -> float | None:
    if not s:
        return None
    m = re.sub(r"[^\d.,]", "", str(s).replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.replace(",", "."))
    except ValueError:
        return None
