"""Авто-тегирование тендеров по нишам (ОКПД2 + ключевые слова)."""

from __future__ import annotations

import logging
import re

from shared.config import ALL_NICHES, NichePreset
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# Предкомпилированные паттерны ключевых слов (ускоряет batch-тегирование)
_NICHE_PATTERNS: dict[str, re.Pattern] = {}


def _get_pattern(niche: NichePreset) -> re.Pattern:
    if niche.tag not in _NICHE_PATTERNS:
        # Экранируем и собираем в одно регулярное выражение
        parts = [re.escape(kw.lower()) for kw in niche.keywords]
        _NICHE_PATTERNS[niche.tag] = re.compile(
            r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)",
            re.IGNORECASE,
        )
    return _NICHE_PATTERNS[niche.tag]


def tag_tender(tender: TenderCreate, niches: list[NichePreset] | None = None) -> list[str]:
    """Определить теги ниш для тендера.

    Проверяет (в порядке приоритета):
    1. Совпадение ОКПД2-кодов тендера с префиксами ниши
    2. Наличие ключевых слов в title + description

    Returns:
        Список тегов (может быть пустым или содержать несколько ниш).
    """
    if niches is None:
        niches = ALL_NICHES

    tags: list[str] = []
    text = f"{tender.title or ''} {tender.description or ''}".lower()

    for niche in niches:
        matched = False

        # Быстрая проверка по ОКПД2
        for code in tender.okpd2_codes:
            for prefix in niche.okpd2_prefixes:
                if code.startswith(prefix):
                    matched = True
                    break
            if matched:
                break

        # Проверка по ключевым словам
        if not matched and text.strip():
            if _get_pattern(niche).search(text):
                matched = True

        if matched:
            tags.append(niche.tag)

    return tags


def tag_tenders_batch(tenders: list[TenderCreate]) -> list[TenderCreate]:
    """Проставить теги ниш для списка тендеров."""
    for tender in tenders:
        tender.niche_tags = tag_tender(tender)

    tagged = sum(1 for t in tenders if t.niche_tags)
    niche_counts: dict[str, int] = {}
    for t in tenders:
        for tag in t.niche_tags:
            niche_counts[tag] = niche_counts.get(tag, 0) + 1

    logger.info(
        f"Tagged {tagged}/{len(tenders)} tenders. "
        f"Top niches: {dict(sorted(niche_counts.items(), key=lambda x: -x[1])[:5])}"
    )
    return tenders
