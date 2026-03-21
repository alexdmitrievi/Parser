"""Нормализация данных с разных площадок в единую схему."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from shared.models import TenderCreate

logger = logging.getLogger(__name__)


def normalize_region(raw: str | None) -> str | None:
    """Нормализовать название региона."""
    if not raw:
        return None

    raw = raw.strip()

    # Частые сокращения
    replacements = {
        "г. Москва": "Москва",
        "город Москва": "Москва",
        "г. Санкт-Петербург": "Санкт-Петербург",
        "Московская обл.": "Московская область",
        "Омская обл.": "Омская область",
        "Новосибирская обл.": "Новосибирская область",
        "Тюменская обл.": "Тюменская область",
        "Свердловская обл.": "Свердловская область",
    }

    for short, full in replacements.items():
        if short.lower() in raw.lower():
            return full

    return raw


def determine_law_type(registry_number: str | None, source: str = "") -> str:
    """Определить тип закона по номеру закупки."""
    if not registry_number:
        return "commercial"

    num = registry_number.strip()

    # 44-ФЗ: номера обычно начинаются с цифр, длина ~19 символов
    if re.match(r"^\d{19}$", num):
        return "44-fz"

    # 223-ФЗ: номера длиной 11 цифр или содержат буквы
    if re.match(r"^\d{11}$", num):
        return "223-fz"

    if source in ("eis",):
        return "44-fz"

    return "commercial"


def normalize_purchase_method(raw: str | None) -> str | None:
    """Нормализовать способ закупки."""
    if not raw:
        return None

    raw_lower = raw.lower()

    if any(w in raw_lower for w in ["аукцион", "auction"]):
        return "auction"
    if any(w in raw_lower for w in ["конкурс", "contest"]):
        return "contest"
    if any(w in raw_lower for w in ["котировк", "quotation"]):
        return "quotation"
    if any(w in raw_lower for w in ["предложен", "proposal"]):
        return "proposal"
    if any(w in raw_lower for w in ["единственн", "single"]):
        return "single"

    return raw


def normalize_tender(tender: TenderCreate) -> TenderCreate:
    """Нормализовать один тендер."""
    tender.customer_region = normalize_region(tender.customer_region)

    if not tender.law_type or tender.law_type == "commercial":
        tender.law_type = determine_law_type(
            tender.registry_number, tender.source_platform
        )

    tender.purchase_method = normalize_purchase_method(tender.purchase_method)

    # Обрезаем слишком длинные названия
    if tender.title and len(tender.title) > 500:
        tender.title = tender.title[:497] + "..."

    return tender


def normalize_batch(tenders: list[TenderCreate]) -> list[TenderCreate]:
    """Нормализовать список тендеров."""
    result = [normalize_tender(t) for t in tenders]
    logger.info(f"Normalized {len(result)} tenders")
    return result
