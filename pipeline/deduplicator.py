"""Дедупликация по registry_number с приоритетом ЕИС и полем sources."""

from __future__ import annotations

import logging
from typing import Any

from shared.constants import PRIMARY_SOURCE_PRIORITY

logger = logging.getLogger(__name__)


def _priority(platform: str) -> int:
    try:
        return PRIMARY_SOURCE_PRIORITY.index(platform)
    except ValueError:
        return len(PRIMARY_SOURCE_PRIORITY)


def merge_tender(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Объединить запись: предпочесть поля от более приоритетного источника."""
    ex_src = str(existing.get("source_platform") or "")
    in_src = str(incoming.get("source_platform") or "")
    primary = existing if _priority(ex_src) <= _priority(in_src) else incoming
    secondary = incoming if primary is existing else existing

    sources = list(
        dict.fromkeys(
            (existing.get("sources") or [])
            + (incoming.get("sources") or [])
            + [ex_src, in_src]
        )
    )
    sources = [s for s in sources if s]

    merged = dict(primary)
    merged["sources"] = sources
    for k, v in secondary.items():
        if v in (None, "", [], {}):
            continue
        if merged.get(k) in (None, "", [], {}):
            merged[k] = v
    merged["source_platform"] = primary.get("source_platform")
    return merged


def prepare_for_insert(
    row: dict[str, Any],
    existing_by_registry: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, str]:
    """
    Вернуть (payload, action): action = 'insert' | 'update' | 'skip'.
    Если дубликат по registry_number — merge, не создавать вторую строку.
    """
    reg = str(row.get("registry_number") or "").strip()
    if not reg:
        return None, "skip"

    src = str(row.get("source_platform") or "unknown")
    row = dict(row)
    row["sources"] = list(dict.fromkeys((row.get("sources") or []) + [src]))

    if not existing_by_registry or reg not in existing_by_registry:
        return row, "insert"

    merged = merge_tender(existing_by_registry[reg], row)
    return merged, "update"
