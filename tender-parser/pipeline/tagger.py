"""Авто-тегирование тендеров по нишам (ОКПД2 + ключевые слова)."""

from __future__ import annotations

import logging

from shared.config import ALL_NICHES, NichePreset
from shared.models import TenderCreate

logger = logging.getLogger(__name__)


def tag_tender(tender: TenderCreate, niches: list[NichePreset] | None = None) -> list[str]:
    """Определить теги ниш для тендера.
    
    Проверяет:
    1. Совпадение ОКПД2 кодов с префиксами ниши
    2. Наличие ключевых слов в title + description
    """
    if niches is None:
        niches = ALL_NICHES

    tags = []
    text = f"{tender.title or ''} {tender.description or ''}".lower()

    for niche in niches:
        matched = False

        # Проверка по ОКПД2
        for code in tender.okpd2_codes:
            for prefix in niche.okpd2_prefixes:
                if code.startswith(prefix):
                    matched = True
                    break
            if matched:
                break

        # Проверка по ключевым словам (если ОКПД2 не совпал)
        if not matched:
            for keyword in niche.keywords:
                if keyword.lower() in text:
                    matched = True
                    break

        if matched:
            tags.append(niche.tag)

    return tags


def tag_tenders_batch(tenders: list[TenderCreate]) -> list[TenderCreate]:
    """Проставить теги для списка тендеров."""
    for tender in tenders:
        tender.niche_tags = tag_tender(tender)
    
    tagged_count = sum(1 for t in tenders if t.niche_tags)
    logger.info(f"Tagged {tagged_count}/{len(tenders)} tenders with niche tags")
    return tenders
