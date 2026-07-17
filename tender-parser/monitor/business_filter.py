"""Бизнес-фильтры закупок из config/filters.yaml.

Логика (see config/filters.yaml):
    (регион ∧ закон ∧ НМЦК в диапазоне)
    ∧ (совпал ОКПД2-префикс ∨ ключевое слово в наименовании)
    ∧ (нет стоп-слов)

Файл перечитывается при каждом вызове load() — цикл мониторинга вызывает
его в начале прохода, поэтому правки применяются без рестарта сервиса.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterable, Optional

import yaml

logger = logging.getLogger("monitor.filters")

# Лёгкий стемминг русских окончаний: "расчистка"/"расчистке" → "расчистк".
# Порядок — от длинных к коротким.
_RU_ENDINGS = (
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
    "ует", "уют", "ание", "ения", "ений",
    "ов", "ев", "ам", "ям", "ах", "ях", "ой", "ей", "ый", "ий",
    "ая", "яя", "ое", "ее", "ые", "ие", "ью",
    "а", "я", "о", "е", "у", "ю", "ы", "и", "ь",
)


def _stem_word(word: str) -> str:
    for suffix in _RU_ENDINGS:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _stem_set(text: str) -> set[str]:
    return {_stem_word(w) for w in re.split(r"[^\wёЁ]+", text.lower()) if w}


def _phrase_in_text(phrase_words: Iterable[str], text_stems: set[str]) -> bool:
    """Все слова фразы (по стемам) встречаются в тексте."""
    return all(_stem_word(w) in text_stems for w in phrase_words)

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "filters.yaml",
)

# Соответствие "44-ФЗ" (в конфиге) ↔ "44-fz" (в БД)
_LAW_ALIASES = {
    "44-фз": "44-fz",
    "223-фз": "223-fz",
    "44-fz": "44-fz",
    "223-fz": "223-fz",
}


class BusinessFilter:
    """Фильтр закупок по конфигу пользователя."""

    def __init__(self, config: dict[str, Any]):
        self.regions = [str(r).strip().lower() for r in (config.get("regions") or [])]
        self.laws = {
            _LAW_ALIASES.get(str(law).strip().lower(), str(law).strip().lower())
            for law in (config.get("laws") or [])
        }
        nmck = config.get("nmck") or {}
        self.nmck_min = nmck.get("min")
        self.nmck_max = nmck.get("max")
        self.okpd2_prefixes = [str(p).strip() for p in (config.get("okpd2_prefixes") or [])]
        # Ключевые/стоп-слова храним как списки слов фразы (матчинг по стемам,
        # чтобы "расчистка территории" находила "...по расчистке территории...")
        self.keywords = [
            str(k).strip().lower().split() for k in (config.get("keywords") or [])
        ]
        self.stop_words = [
            str(s).strip().lower().split() for s in (config.get("stop_words") or [])
        ]

    # --------------- проверки ---------------

    def _region_ok(self, tender: dict[str, Any]) -> bool:
        if not self.regions:
            return True
        region = (tender.get("customer_region") or "").strip().lower()
        if not region:
            return False
        # Сравнение по первому слову: "омская область" == "омская обл",
        # но НЕ "томская область" (подстрочное сравнение здесь опасно).
        region_first = region.split()[0]
        return any(r.split()[0] == region_first for r in self.regions if r)

    def _law_ok(self, tender: dict[str, Any]) -> bool:
        if not self.laws:
            return True
        law = (tender.get("law_type") or "").strip().lower()
        return law in self.laws

    def _nmck_ok(self, tender: dict[str, Any]) -> bool:
        nmck = tender.get("nmck")
        if nmck is None:
            return False
        try:
            nmck = float(nmck)
        except (TypeError, ValueError):
            return False
        if self.nmck_min is not None and nmck < float(self.nmck_min):
            return False
        if self.nmck_max is not None and nmck > float(self.nmck_max):
            return False
        return True

    def _subject_ok(self, tender: dict[str, Any]) -> bool:
        """ОКПД2-префикс ∨ ключевое слово в наименовании."""
        codes = tender.get("okpd2_codes") or []
        for code in codes:
            for prefix in self.okpd2_prefixes:
                if str(code).startswith(prefix):
                    return True
        title_stems = _stem_set(tender.get("title") or "")
        return any(_phrase_in_text(kw, title_stems) for kw in self.keywords)

    def _stop_words_ok(self, tender: dict[str, Any]) -> bool:
        title_stems = _stem_set(tender.get("title") or "")
        return not any(_phrase_in_text(sw, title_stems) for sw in self.stop_words)

    def matches(self, tender: dict[str, Any]) -> bool:
        return (
            self._region_ok(tender)
            and self._law_ok(tender)
            and self._nmck_ok(tender)
            and self._subject_ok(tender)
            and self._stop_words_ok(tender)
        )

    # --------------- загрузка ---------------

    @classmethod
    def load(cls, path: Optional[str] = None) -> "BusinessFilter":
        """Прочитать конфиг с диска. Вызывается на каждом цикле."""
        path = path or os.environ.get("FILTERS_CONFIG", DEFAULT_CONFIG_PATH)
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        logger.info(
            f"Filters loaded from {path}: regions={config.get('regions')}, "
            f"nmck={config.get('nmck')}, {len(config.get('keywords') or [])} keywords, "
            f"{len(config.get('okpd2_prefixes') or [])} OKPD2 prefixes"
        )
        return cls(config)
