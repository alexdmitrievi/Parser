"""Базовый миксин для скраперов б/у спецтехники CAT (СНГ).

Общая логика: маппинг dict → TenderCreate, парсинг цен с валютой,
нормализация названий моделей Caterpillar.
"""

from __future__ import annotations

import re
from typing import Optional

from shared.models import TenderCreate


# Паттерны валют
CURRENCY_PATTERNS = {
    "USD": [r"\$", r"USD", r"U\.S\.\s*Dollar"],
    "EUR": [r"\u20AC", r"EUR"],
    "RUB": [r"\u20BD", r"RUB", r"\u0440\u0443\u0431"],
    "KZT": [r"\u20B8", r"KZT", r"\u0442\u0435\u043D\u0433\u0435", r"\u0442\u04A3"],
}


def detect_currency(text: str) -> str:
    """Определить валюту из строки с ценой."""
    if not text:
        return "USD"
    for currency, patterns in CURRENCY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return currency
    return "USD"


def parse_price(text: str) -> Optional[float]:
    """Извлечь числовое значение цены из строки."""
    if not text:
        return None
    # Убираем всё кроме цифр, точки и запятой
    cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", ""))
    if not cleaned:
        return None
    # Обработка европейского формата: 1.234.567,89 → 1234567.89
    if "," in cleaned and "." in cleaned:
        if cleaned.rindex(",") > cleaned.rindex("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # 1234,56 или 1,234,567
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def parse_price_with_currency(text: str) -> tuple[Optional[float], str]:
    """Извлечь цену и валюту из строки."""
    currency = detect_currency(text)
    price = parse_price(text)
    return price, currency


def normalize_cat_title(title: str) -> str:
    """Нормализовать название модели CAT."""
    if not title:
        return title
    # Раскрываем сокращения: CAT → Caterpillar (только в начале)
    title = re.sub(r"^CAT\b", "Caterpillar", title, flags=re.IGNORECASE)
    return title.strip()


def to_tender(
    *,
    platform: str,
    title: str,
    price: Optional[float] = None,
    currency: str = "USD",
    region: Optional[str] = None,
    url: Optional[str] = None,
    registry_number: Optional[str] = None,
    description: Optional[str] = None,
) -> TenderCreate:
    """Создать TenderCreate из данных объявления спецтехники."""
    return TenderCreate(
        source_platform=platform,
        registry_number=registry_number,
        law_type="cis_cat",
        title=normalize_cat_title(title),
        description=description,
        customer_name=None,
        customer_region=region,
        nmck=price,
        currency=currency,
        original_url=url,
        niche_tags=["equipment"],
    )
