"""Нормализация и теги для dict-строк парсеров (альт. путь scrapers/scripts/run_parser)."""

from __future__ import annotations

import logging
import re
from typing import Any

from shared.time_utils import now_utc, parse_datetime_ru, to_utc

logger = logging.getLogger(__name__)

REGION_ALIASES: dict[str, str] = {
    "москва": "Москва",
    "г москва": "Москва",
    "г. москва": "Москва",
    "московская область": "Московская область",
    "московская обл": "Московская область",
    "санкт-петербург": "Санкт-Петербург",
    "спб": "Санкт-Петербург",
    "омская область": "Омская область",
    "омск": "Омск",
}


def normalize_region(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"\s+", " ", str(raw).strip().lower())
    return REGION_ALIASES.get(key, str(raw).strip())


def normalize_tender(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Вернуть нормализованный dict или None если отсеять."""
    title = (raw.get("title") or "").strip()
    if not title:
        return None

    status = (raw.get("status") or "active").lower()
    deadline = raw.get("submission_deadline")
    if deadline is None and raw.get("submission_deadline_raw"):
        deadline = parse_datetime_ru(str(raw["submission_deadline_raw"]))
    if isinstance(deadline, str):
        deadline = parse_datetime_ru(deadline)
    deadline = to_utc(deadline) if deadline else None

    if status == "active" and deadline and deadline < now_utc():
        return None

    region = normalize_region(raw.get("customer_region"))
    nmck = raw.get("nmck")
    if nmck is not None:
        try:
            nmck = float(nmck)
        except (TypeError, ValueError):
            nmck = None

    return {
        "registry_number": str(raw.get("registry_number") or "").strip() or title[:64],
        "title": title,
        "nmck": nmck,
        "customer_name": raw.get("customer_name"),
        "customer_region": region,
        "submission_deadline": deadline,
        "law_type": raw.get("law_type"),
        "status": status,
        "source_platform": raw.get("source_platform") or "unknown",
        "sources": raw.get("sources") or [raw.get("source_platform") or "unknown"],
        "niche_tags": raw.get("niche_tags") or [],
        "description": raw.get("description"),
        "documents_urls": raw.get("documents_urls") or [],
        "external_url": raw.get("external_url"),
        "raw_payload": raw.get("raw_payload") or {},
    }


FURNITURE_OKPD_HINTS = ("31", "32.5", "31.0", "31.01")
CONSTRUCTION_KEYWORDS = (
    "строител",
    "ремонт",
    "подряд",
    "капитальн",
    "текущий ремонт",
    "монтаж",
    "отделк",
)
FURNITURE_KEYWORDS = (
    "мебел",
    "стол",
    "стул",
    "шкаф",
    "офисная мебель",
    "кресл",
    "перегородк",
)


def _text_blob(t: dict[str, Any]) -> str:
    parts = [
        str(t.get("title") or ""),
        str(t.get("description") or ""),
        " ".join(t.get("niche_tags") or []),
        str(t.get("raw_payload") or ""),
    ]
    okpd = t.get("okpd2") or t.get("okpd")
    if okpd:
        parts.append(str(okpd))
    return " ".join(parts).lower()


def tag_tender(tender: dict[str, Any]) -> dict[str, Any]:
    """Добавить niche_tags с учётом 223-ФЗ и ключевых слов."""
    text = _text_blob(tender)
    tags: list[str] = list(tender.get("niche_tags") or [])

    law = str(tender.get("law_type") or "").lower()
    if "223" in law:
        for kw in FURNITURE_KEYWORDS:
            if kw in text:
                if "furniture" not in tags:
                    tags.append("furniture")
                break
        for kw in CONSTRUCTION_KEYWORDS:
            if kw in text:
                if "construction" not in tags:
                    tags.append("construction")
                break

    for hint in FURNITURE_OKPD_HINTS:
        if hint in text:
            if "furniture" not in tags:
                tags.append("furniture")
            break

    if re.search(
        r"мебел|столы|стулья|шкаф|офисн", text
    ):
        if "furniture" not in tags:
            tags.append("furniture")
    if re.search(r"строител|ремонт|подряд|монтаж|капитальн", text):
        if "construction" not in tags:
            tags.append("construction")

    tender = dict(tender)
    tender["niche_tags"] = sorted(set(tags))
    return tender
