"""Помощники для разбора HTML."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def text(el: Tag | None) -> str | None:
    if el is None:
        return None
    t = el.get_text(" ", strip=True)
    return t or None


def first_href(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    a = tag.find("a", href=True)
    if a and isinstance(a, Tag):
        return str(a.get("href"))
    if tag.name == "a" and tag.get("href"):
        return str(tag.get("href"))
    return None


def abs_url(base: str, href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        from urllib.parse import urljoin

        return urljoin(base, href)
    return href


PRICE_RE = re.compile(r"[\d\s]+(?:[.,]\d+)?")


def parse_price(text_val: str | None) -> float | None:
    if not text_val:
        return None
    m = re.sub(r"[^\d.,]", "", text_val.replace(" ", ""))
    if not m:
        return None
    m = m.replace(",", ".")
    try:
        return float(m)
    except ValueError:
        return None
