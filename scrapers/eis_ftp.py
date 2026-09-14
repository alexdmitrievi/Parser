"""Парсер FTP-выгрузок ЕИС (zakupki.gov.ru).

Основной и самый надёжный источник тендеров.
FTP содержит XML-файлы в ZIP-архивах по регионам.
"""

from __future__ import annotations

import ftplib
import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from shared.config import get_config
from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Namespace'ы XML ЕИС (основные)
NS = {
    "ns": "http://zakupki.gov.ru/oos/types/1",
    "oos": "http://zakupki.gov.ru/oos/types/1",
    "ns2": "http://zakupki.gov.ru/oos/printform/1",
}

# Пути на FTP для разных типов извещений
FTP_PATHS = {
    "notifications": "fcs_regions/{region}/notifications/currMonth/",
    "notifications_prev": "fcs_regions/{region}/notifications/prevMonth/",
}


class EisFtpScraper(BaseScraper):
    """Парсер FTP zakupki.gov.ru."""

    platform = "eis"
    min_delay = 0.5  # FTP не банит, задержки минимальные
    max_delay = 1.5

    def __init__(self, regions: Optional[list[str]] = None):
        super().__init__()
        cfg = get_config()
        self.ftp_host = cfg["eis_ftp_host"]
        # Если регионы не указаны, парсим основные
        self.regions = regions or [
            "Omskaya_obl",
            "Novosibirskaya_obl",
            "Tyumenskaya_obl",
            "Moskva",
            "Sankt-Peterburg",
            "Sverdlovskaya_obl",
        ]

    def _connect_ftp(self) -> ftplib.FTP:
        """Подключиться к FTP серверу ЕИС."""
        logger.info(f"Connecting to FTP {self.ftp_host}")
        ftp = ftplib.FTP(self.ftp_host, timeout=60)
        ftp.login()  # Anonymous login
        ftp.encoding = "utf-8"
        return ftp

    def _list_zip_files(self, ftp: ftplib.FTP, path: str) -> list[str]:
        """Получить список ZIP-файлов в директории."""
        try:
            ftp.cwd(path)
            files = []
            ftp.retrlines("LIST", lambda line: files.append(line.split()[-1]))
            return [f for f in files if f.endswith(".xml.zip")]
        except ftplib.error_perm as e:
            logger.warning(f"FTP path not found: {path} — {e}")
            return []

    def _download_zip(self, ftp: ftplib.FTP, filename: str) -> bytes:
        """Скачать ZIP-файл в память."""
        buffer = io.BytesIO()
        ftp.retrbinary(f"RETR {filename}", buffer.write)
        buffer.seek(0)
        return buffer.read()

    def _extract_xml_from_zip(self, zip_bytes: bytes) -> list[str]:
        """Извлечь XML-файлы из ZIP-архива."""
        xml_contents = []
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        xml_contents.append(zf.read(name).decode("utf-8", errors="replace"))
        except zipfile.BadZipFile:
            logger.warning("Invalid ZIP file, skipping")
        return xml_contents

    def _parse_xml_notification(self, xml_str: str) -> Optional[TenderCreate]:
        """Распарсить одно XML-извещение в TenderCreate."""
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            logger.debug(f"XML parse error: {e}")
            return None

        # Ищем основные элементы (структура может варьироваться)
        tender_data = {}

        # Номер закупки
        for tag in ["purchaseNumber", "registrationNumber", "regNum"]:
            el = root.find(f".//{{{NS['ns']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and el.text:
                tender_data["registry_number"] = el.text.strip()
                break

        if not tender_data.get("registry_number"):
            # Без номера закупки нет смысла сохранять
            return None

        # Наименование
        for tag in ["purchaseObjectInfo", "name", "subject"]:
            el = root.find(f".//{{{NS['ns']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and el.text:
                tender_data["title"] = el.text.strip()
                break

        if not tender_data.get("title"):
            return None

        # Заказчик
        for tag in ["fullName", "organizationName"]:
            el = root.find(f".//{{{NS['ns']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and el.text:
                tender_data["customer_name"] = el.text.strip()
                break

        # ИНН заказчика
        for tag in ["INN", "inn"]:
            el = root.find(f".//{{{NS['ns']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and el.text:
                tender_data["customer_inn"] = el.text.strip()
                break

        # НМЦК
        for tag in ["maxPrice", "lot/maxPrice", "maximumPrice"]:
            parts = tag.split("/")
            el = root
            for part in parts:
                if el is not None:
                    el = el.find(f".//{{{NS['ns']}}}{part}") or el.find(f".//{part}")
            if el is not None and el.text:
                try:
                    tender_data["nmck"] = float(el.text.strip())
                except ValueError:
                    pass
                break

        # Дата публикации
        for tag in ["publishDTInEIS", "publishDate", "docPublishDate"]:
            el = root.find(f".//{{{NS['ns']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and el.text:
                try:
                    tender_data["publish_date"] = datetime.fromisoformat(
                        el.text.strip().replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
                break

        # Дедлайн подачи заявок
        for tag in ["applEndDate", "submissionCloseDateTime", "endDate"]:
            el = root.find(f".//{{{NS['ns']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and el.text:
                try:
                    tender_data["submission_deadline"] = datetime.fromisoformat(
                        el.text.strip().replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
                break

        # ОКПД2
        okpd2_codes = []
        for el in root.iter():
            if "OKPD2" in el.tag or "okpd2" in el.tag:
                code_el = el.find(f".//{{{NS['ns']}}}code") or el.find(".//code")
                if code_el is not None and code_el.text:
                    okpd2_codes.append(code_el.text.strip())
        tender_data["okpd2_codes"] = list(set(okpd2_codes))

        # Способ закупки (по типу документа)
        root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        method_map = {
            "epNotification": "auction",
            "notificationEF": "auction",
            "fcsNotificationEF": "auction",
            "notificationOK": "contest",
            "fcsNotificationOK": "contest",
            "notificationZK": "quotation",
            "fcsNotificationZK": "quotation",
            "notificationZP": "proposal",
            "fcsNotificationZP": "proposal",
            "notificationEP": "single",
        }
        tender_data["purchase_method"] = method_map.get(root_tag, "other")

        # Определяем тип закона
        tender_data["law_type"] = "44-fz"  # FTP ЕИС — по умолчанию 44-ФЗ

        # URL на площадке
        reg_num = tender_data["registry_number"]
        tender_data["original_url"] = (
            f"https://zakupki.gov.ru/epz/order/notice/ea20/view/"
            f"common-info.html?regNumber={reg_num}"
        )

        return TenderCreate(
            source_platform=self.platform,
            **tender_data,
        )

    def parse_tenders(self, xml_strings: list[str]) -> list[TenderCreate]:
        """Распарсить список XML-строк в тендеры."""
        tenders = []
        for xml_str in xml_strings:
            tender = self._parse_xml_notification(xml_str)
            if tender:
                tenders.append(tender)
        return tenders

    def run(self, max_files_per_region: int = 50, **kwargs) -> list[TenderCreate]:
        """Запустить парсинг FTP ЕИС.
        
        Args:
            max_files_per_region: Максимум ZIP-файлов на регион (для ограничения нагрузки).
        """
        all_tenders: list[TenderCreate] = []

        try:
            ftp = self._connect_ftp()
        except Exception as e:
            logger.error(f"Failed to connect to FTP: {e}")
            return []

        try:
            for region in self.regions:
                logger.info(f"Parsing region: {region}")
                ftp_path = f"/fcs_regions/{region}/notifications/currMonth/"

                zip_files = self._list_zip_files(ftp, ftp_path)
                logger.info(f"  Found {len(zip_files)} ZIP files")

                for zip_file in zip_files[:max_files_per_region]:
                    try:
                        zip_bytes = self._download_zip(ftp, zip_file)
                        xml_contents = self._extract_xml_from_zip(zip_bytes)
                        tenders = self.parse_tenders(xml_contents)
                        all_tenders.extend(tenders)
                        logger.info(f"  {zip_file}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error processing {zip_file}: {e}")
                        continue

                logger.info(f"  Region {region}: {len(all_tenders)} total tenders so far")

        except Exception as e:
            logger.error(f"FTP parsing error: {e}")
        finally:
            try:
                ftp.quit()
            except Exception:
                pass

        logger.info(f"EIS FTP: Total {len(all_tenders)} tenders parsed")
        return all_tenders
