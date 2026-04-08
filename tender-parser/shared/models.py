"""Pydantic-модели данных: тендеры, подписки, поиск."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TenderCreate(BaseModel):
    """Модель для вставки тендера в БД."""
    source_platform: str
    registry_number: Optional[str] = None
    law_type: Optional[str] = None  # '44-fz', '223-fz', 'commercial'
    purchase_method: Optional[str] = None
    title: str
    description: Optional[str] = None
    customer_name: Optional[str] = None
    customer_inn: Optional[str] = None
    customer_region: Optional[str] = None
    okpd2_codes: list[str] = Field(default_factory=list)
    nmck: Optional[float] = None
    currency: str = "RUB"
    publish_date: Optional[datetime] = None
    submission_deadline: Optional[datetime] = None
    auction_date: Optional[datetime] = None
    status: str = "active"
    documents_urls: list[dict] = Field(default_factory=list)
    contact_info: dict = Field(default_factory=dict)
    original_url: Optional[str] = None
    raw_data: Optional[dict] = None
    niche_tags: list[str] = Field(default_factory=list)


class TenderResponse(BaseModel):
    """Модель тендера для ответа API."""
    id: str
    source_platform: str
    registry_number: Optional[str] = None
    law_type: Optional[str] = None
    purchase_method: Optional[str] = None
    title: str
    description: Optional[str] = None
    customer_name: Optional[str] = None
    customer_region: Optional[str] = None
    okpd2_codes: list[str] = Field(default_factory=list)
    nmck: Optional[float] = None
    currency: str = "RUB"
    publish_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    status: str = "active"
    original_url: Optional[str] = None
    niche_tags: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None


class SubscriptionCreate(BaseModel):
    """Модель для создания подписки."""
    telegram_user_id: int
    name: str
    keywords: list[str] = Field(default_factory=list)
    okpd2_prefixes: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    min_nmck: Optional[float] = None
    max_nmck: Optional[float] = None
    law_types: list[str] = Field(default_factory=list)
    niche_tags: list[str] = Field(default_factory=list)


class FundingProgramCreate(BaseModel):
    """Модель для вставки программы финансирования МСП."""
    source_platform: str
    external_id: Optional[str] = None
    program_name: str
    program_type: str  # grant, loan, subsidy, guarantee, microloan, compensation
    organizer_name: Optional[str] = None
    organizer_url: Optional[str] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    rate: Optional[float] = None
    term_months: Optional[int] = None
    regions: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    requirements: Optional[str] = None
    target_audience: Optional[str] = None
    deadline: Optional[datetime] = None
    status: str = "active"
    original_url: str
    publish_date: Optional[datetime] = None


class FundingProgramResponse(BaseModel):
    """Модель программы финансирования для ответа API."""
    id: str
    source_platform: str
    external_id: Optional[str] = None
    program_name: str
    program_type: str
    organizer_name: Optional[str] = None
    organizer_url: Optional[str] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    rate: Optional[float] = None
    term_months: Optional[int] = None
    regions: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    requirements: Optional[str] = None
    target_audience: Optional[str] = None
    deadline: Optional[str] = None
    status: str = "active"
    original_url: str
    publish_date: Optional[str] = None
    created_at: Optional[str] = None


class FundingSearchFilters(BaseModel):
    """Фильтры поиска программ финансирования."""
    query: Optional[str] = None
    region: Optional[str] = None
    program_type: Optional[str] = None
    industry: Optional[str] = None
    amount_max: Optional[float] = None
    status: str = "active"
    page: int = 1
    per_page: int = 12


class SearchFilters(BaseModel):
    """Фильтры поиска тендеров."""
    query: Optional[str] = None
    region: Optional[str] = None
    min_nmck: Optional[float] = None
    max_nmck: Optional[float] = None
    okpd2: Optional[str] = None
    niche: Optional[str] = None
    status: str = "active"
    law_type: Optional[str] = None
    purchase_method: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    source_platform: Optional[str] = None
    sort_by: str = "created_at"
    page: int = 1
    per_page: int = 5

    @classmethod
    def from_state_dict(
        cls,
        filters: dict,
        page: int,
        per_page: int = 5,
    ) -> "SearchFilters":
        """Собрать из state['filters'] (бот) или JSON тела запроса (веб)."""
        return cls(
            query=filters.get("query"),
            region=filters.get("region"),
            min_nmck=filters.get("min_nmck"),
            max_nmck=filters.get("max_nmck"),
            niche=filters.get("niche"),
            okpd2=filters.get("okpd2"),
            law_type=filters.get("law_type") or filters.get("law"),
            status=filters.get("status") or "active",
            purchase_method=filters.get("purchase_method"),
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            source_platform=filters.get("source_platform"),
            sort_by=filters.get("sort_by") or "created_at",
            page=page,
            per_page=per_page,
        )
