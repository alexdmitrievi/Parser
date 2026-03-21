"""Скачивание PDF/DOCX и извлечение текста в description (для нишевых тендеров)."""

from __future__ import annotations

import io
import logging
from typing import Any

import httpx
import pdfplumber
from docx import Document

from pipeline.tagger import tag_tender
from pipeline.normalizer import normalize_tender

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


def _extract_pdf(data: bytes) -> str:
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:30]:
            t = page.extract_text() or ""
            if t.strip():
                out.append(t.strip())
    return "\n\n".join(out)


def _extract_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def download_and_extract(url: str) -> str | None:
    try:
        with httpx.Client(timeout=60.0, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.content
    except Exception as e:
        logger.debug("download failed %s: %s", url, e)
        return None
    lower = url.lower()
    if lower.endswith(".pdf") or data[:4] == b"%PDF":
        try:
            return _extract_pdf(data)
        except Exception as e:
            logger.debug("pdf extract %s: %s", url, e)
            return None
    if lower.endswith(".docx"):
        try:
            return _extract_docx(data)
        except Exception as e:
            logger.debug("docx extract %s: %s", url, e)
            return None
    return None


def enrich_tender_description(tender: dict[str, Any]) -> dict[str, Any]:
    """
    Если niche_tags не пустой — скачать документы и дописать description.
    Затем пересчитать теги.
    """
    tags = tender.get("niche_tags") or []
    if not tags:
        return tender
    urls = tender.get("documents_urls") or []
    if not urls:
        return tender
    chunks: list[str] = []
    for u in urls[:5]:
        if not isinstance(u, str):
            continue
        text = download_and_extract(u)
        if text:
            chunks.append(text[:12000])
    if not chunks:
        return tender
    merged = (tender.get("description") or "").strip()
    block = "\n\n---\n\n".join(chunks)
    tender = dict(tender)
    tender["description"] = (merged + "\n\n" + block).strip()[:50000]
    tender = tag_tender(tender)
    return tender


def enrich_batch(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw_items:
        n = normalize_tender(item)
        if not n:
            continue
        n = tag_tender(n)
        n = enrich_tender_description(n)
        out.append(n)
    return out
