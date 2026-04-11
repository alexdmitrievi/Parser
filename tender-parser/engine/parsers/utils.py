"""Shared parsing utilities: price, date, number, region extraction.

Centralized here so every source adapter uses the same logic.
No source-specific code — only generic Russian-language procurement data parsing.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


# ─────────────────────── Price Parsing ───────────────────────

# Characters to strip from price strings
_PRICE_STRIP_RE = re.compile(r"[^\d.,]")
# Multiple dots pattern (e.g., "1.234.567,89" European format)
_MULTI_DOT_RE = re.compile(r"(\d)\.(\d{3})(?:[.,]|$)")


def parse_price(text: str | None) -> Optional[float]:
    """Parse Russian/European price formats to float.

    Handles:
        "1 234 567,89 ₽"  → 1234567.89
        "1.234.567,89"     → 1234567.89
        "545 916.00"       → 545916.0
        "1234567"          → 1234567.0
        "без указания"     → None
    """
    if not text:
        return None

    text = text.strip()
    if not text:
        return None

    # Filtered out known "no price" patterns
    low = text.lower()
    if any(kw in low for kw in ["без указания", "не указан", "по запросу", "договорная"]):
        return None

    # Remove everything except digits, dots, commas
    cleaned = text.replace("\xa0", "").replace(" ", "")
    cleaned = _PRICE_STRIP_RE.sub("", cleaned)

    # Strip leading/trailing dots and commas (artifacts from "руб.", etc.)
    cleaned = cleaned.strip(".,")

    if not cleaned:
        return None

    # Detect European format: "1.234.567,89"
    # If more than one dot, treat dots as thousand separators
    dot_count = cleaned.count(".")
    comma_count = cleaned.count(",")

    if dot_count > 1:
        # "1.234.567,89" → remove dots, replace comma with dot
        cleaned = cleaned.replace(".", "")
        cleaned = cleaned.replace(",", ".")
    elif dot_count == 1 and comma_count == 1:
        # "1.234,56" → dot is thousands, comma is decimal
        if cleaned.index(".") < cleaned.index(","):
            cleaned = cleaned.replace(".", "")
            cleaned = cleaned.replace(",", ".")
        else:
            # "1,234.56" — American format
            cleaned = cleaned.replace(",", "")
    elif comma_count >= 1:
        # "1234,56" → comma is decimal separator
        cleaned = cleaned.replace(",", ".")
    # else: "1234.56" — already correct

    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


# ─────────────────────── Date Parsing ───────────────────────

RUSSIAN_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
    "янв": "01", "фев": "02", "мар": "03", "апр": "04",
    "май": "05", "июн": "06", "июл": "07", "авг": "08",
    "сен": "09", "окт": "10", "ноя": "11", "дек": "12",
}

# DD.MM.YYYY HH:MM or DD.MM.YYYY
_DATE_RE = re.compile(
    r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})"
    r"(?:\s+(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?)?"
)

# YYYY-MM-DD (ISO)
_ISO_DATE_RE = re.compile(
    r"(\d{4})-(\d{1,2})-(\d{1,2})"
    r"(?:[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)

# "12 января 2025"
_RUSSIAN_DATE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(RUSSIAN_MONTHS.keys()) + r")\s+(\d{4})"
    r"(?:\s+(\d{1,2})[:\.](\d{2}))?",
    re.IGNORECASE,
)


def parse_date(text: str | None) -> Optional[datetime]:
    """Parse date from Russian/ISO formats.

    Handles:
        "25.12.2025 14:30"
        "25/12/2025"
        "2025-12-25T14:30:00"
        "25 декабря 2025"
        "25 дек 2025 14:30"
    """
    if not text:
        return None

    text = text.strip()
    if not text:
        return None

    # Try Russian text date first
    m = _RUSSIAN_DATE_RE.search(text)
    if m:
        day, month_name, year = m.group(1), m.group(2).lower(), m.group(3)
        month = RUSSIAN_MONTHS.get(month_name)
        if month:
            hour = m.group(4) or "0"
            minute = m.group(5) or "0"
            try:
                return datetime(int(year), int(month), int(day), int(hour), int(minute))
            except ValueError:
                pass

    # Try DD.MM.YYYY
    m = _DATE_RE.search(text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        hour = m.group(4) or "0"
        minute = m.group(5) or "0"
        second = m.group(6) or "0"
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
        except ValueError:
            pass

    # Try ISO format
    m = _ISO_DATE_RE.search(text)
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
        hour = m.group(4) or "0"
        minute = m.group(5) or "0"
        second = m.group(6) or "0"
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
        except ValueError:
            pass

    return None


# ─────────────────────── Registry Number Parsing ───────────────────────

_REGISTRY_NUM_RE = re.compile(r"\d{7,19}")


def parse_registry_number(text: str | None, url: str = "") -> Optional[str]:
    """Extract registry/tender number from text or URL.

    Looks for numeric sequences of 7-19 digits (covers 44-FZ, 223-FZ, commercial).
    """
    if not text and not url:
        return None

    combined = f"{text or ''} {url}"
    m = _REGISTRY_NUM_RE.search(combined)
    return m.group(0) if m else None


# ─────────────────────── Text Cleaning ───────────────────────


def clean_text(text: str | None, max_length: int = 0) -> str:
    """Clean and normalize text: strip, collapse whitespace, optional truncation."""
    if not text:
        return ""
    # Replace non-breaking spaces, tabs, newlines with regular spaces
    cleaned = text.replace("\xa0", " ").replace("\t", " ").replace("\n", " ")
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1] + "…"
    return cleaned


# ─────────────────────── Region Detection ───────────────────────

# Common region aliases
_REGION_ALIASES: dict[str, str] = {
    "г. москва": "Москва",
    "город москва": "Москва",
    "г москва": "Москва",
    "г. санкт-петербург": "Санкт-Петербург",
    "город санкт-петербург": "Санкт-Петербург",
    "г. севастополь": "Севастополь",
    "московская обл": "Московская область",
    "московская обл.": "Московская область",
    "ленинградская обл": "Ленинградская область",
    "ленинградская обл.": "Ленинградская область",
    "омская обл": "Омская область",
    "омская обл.": "Омская область",
    "новосибирская обл": "Новосибирская область",
    "новосибирская обл.": "Новосибирская область",
    "тюменская обл": "Тюменская область",
    "тюменская обл.": "Тюменская область",
    "свердловская обл": "Свердловская область",
    "свердловская обл.": "Свердловская область",
    # CIS
    "нур-султан": "Астана",
    "г. астана": "Астана",
    "г. алматы": "Алматы",
    "г. минск": "Минск",
    "г. бишкек": "Бишкек",
    "г. ташкент": "Ташкент",
}


def normalize_region(raw: str | None) -> Optional[str]:
    """Normalize region name via alias map. Returns cleaned name or original."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None

    low = raw.lower()
    for alias, canonical in _REGION_ALIASES.items():
        if alias in low:
            return canonical

    # Strip leading "г." or digit prefix (e.g., "77. г. Москва")
    cleaned = re.sub(r"^\d+\.\s*", "", raw)
    cleaned = re.sub(r"^г\.\s*", "", cleaned).strip()
    return cleaned or raw


def extract_region_from_text(text: str) -> Optional[str]:
    """Try to find a Russian region name in free text.

    Uses word-boundary prefix matching to avoid false positives
    (e.g., "омск" inside "костромской").
    """
    if not text:
        return None

    # Import here to avoid circular dependency at module level
    from shared.constants import RUSSIAN_REGIONS

    text_lower = text.lower()
    words = re.split(r'[\s,;.\(\)\-/«»""'']+', text_lower)
    words = [w for w in words if w]

    # Sort regions by name length descending so longer names match first
    for region in sorted(RUSSIAN_REGIONS, key=len, reverse=True):
        # Get the distinguishing word from region name
        for part in region.lower().split():
            if part in ("край", "область", "округ", "республика",
                        "автономная", "автономный", "еврейская", "город"):
                continue
            # Stem the region name part
            stem = part
            for suffix in ("ская", "ский", "ском", "ских",
                           "ная", "ный", "ном", "ных",
                           "кая", "кий", "ком", "ких"):
                if part.endswith(suffix) and len(part) - len(suffix) >= 3:
                    stem = part[:-len(suffix)]
                    break
            # Word-boundary prefix match: keyword must match START of a word
            if any(w.startswith(stem) for w in words):
                return region

    return None
