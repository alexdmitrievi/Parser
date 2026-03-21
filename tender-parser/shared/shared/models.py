"""Модели для поиска и API."""

from __future__ import annotations

from pydantic import BaseModel


class SearchFilters(BaseModel):
    """Фильтры поиска тендеров (бот и API)."""

    query: str | None = None
    region: str | None = None
    min_nmck: float | None = None
    max_nmck: float | None = None
    niche: str | None = None
    law: str | None = None
    status: str = "active"
    page: int = 1
    per_page: int = 5

    @classmethod
    def from_state_dict(cls, filters: dict, page: int, per_page: int = 5) -> "SearchFilters":
        """Собрать из сохранённого state['filters'] и номера страницы."""
        return cls(
            query=filters.get("query"),
            region=filters.get("region"),
            min_nmck=filters.get("min_nmck"),
            max_nmck=filters.get("max_nmck"),
            niche=filters.get("niche"),
            law=filters.get("law"),
            status=filters.get("status") or "active",
            page=page,
            per_page=per_page,
        )
