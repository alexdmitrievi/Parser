"""Law type detection from registry numbers and source hints."""

from __future__ import annotations

import re
from typing import Optional


# 44-ФЗ: 19-digit numbers (government procurement)
_44FZ_RE = re.compile(r"^\d{19}$")

# 223-ФЗ: 11-digit numbers (state companies)
_223FZ_RE = re.compile(r"^\d{11}$")

# ПП615: specific prefix patterns
_PP615_RE = re.compile(r"^\d{18}[A-Za-z].*")

# Sources that are always 44-FZ
_44FZ_SOURCES = {"eis", "eis_ftp", "eis_api", "roseltorg", "sberbank_ast", "rts_tender"}

# Sources that are always 223-FZ
_223FZ_SOURCES = {"gazprom", "rosatom", "rosneft", "lukoil", "nornickel", "mts", "tektorg"}


def detect_law_type(
    registry_number: str | None = None,
    source_platform: str = "",
    title: str = "",
    description: str = "",
) -> str:
    """Determine law type from registry number pattern, source, and text clues.

    Returns: '44-fz', '223-fz', 'pp615', or 'commercial'
    """
    # 1. Source-based detection (most reliable)
    if source_platform in _44FZ_SOURCES:
        return "44-fz"
    if source_platform in _223FZ_SOURCES:
        return "223-fz"

    # 2. Registry number pattern
    if registry_number:
        num = registry_number.strip()
        if _44FZ_RE.match(num):
            return "44-fz"
        if _223FZ_RE.match(num):
            return "223-fz"
        if _PP615_RE.match(num):
            return "pp615"

    # 3. Text clues
    combined = f"{title} {description}".lower()
    if "44-фз" in combined or "44 фз" in combined:
        return "44-fz"
    if "223-фз" in combined or "223 фз" in combined:
        return "223-fz"
    if "пп615" in combined or "пп 615" in combined:
        return "pp615"

    return "commercial"
