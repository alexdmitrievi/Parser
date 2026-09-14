"""Purchase method normalization: Russian names to canonical English codes."""

from __future__ import annotations

from typing import Optional

# Mapping: keyword → canonical method
_METHOD_MAP: list[tuple[list[str], str]] = [
    (["электронный аукцион", "аукцион", "auction"], "auction"),
    (["открытый конкурс", "конкурс", "contest"], "contest"),
    (["запрос котировок", "ценовых котировок", "котировк", "quotation"], "quotation"),
    (["запрос предложений", "предложен", "proposal"], "proposal"),
    (["единственный поставщик", "единственн", "single"], "single_source"),
    (["закупка у единственного", "прямая закупка"], "single_source"),
    (["конкурс с ограниченным участием"], "limited_contest"),
    (["двухэтапный конкурс"], "two_stage_contest"),
]


def normalize_purchase_method(raw: str | None) -> Optional[str]:
    """Normalize Russian procurement method to canonical code."""
    if not raw:
        return None

    low = raw.lower().strip()
    if not low:
        return None

    for keywords, canonical in _METHOD_MAP:
        if any(kw in low for kw in keywords):
            return canonical

    return raw  # return original if unknown
