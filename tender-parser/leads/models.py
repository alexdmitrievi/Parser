"""Модели домена leads.

``LeadCompany`` — карточка компании, ``LeadEmail`` — один найденный адрес.
Одна компания может иметь несколько адресов; в CSV-экспорт уходит по строке
на адрес.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    """Текущее время в UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


# Ролевые префиксы: обезличенные корпоративные ящики. Только они по умолчанию
# уходят в экспорт — см. требования PIPL в docs/LEADS.md.
ROLE_LOCAL_PARTS = frozenset({
    "info", "sales", "export", "trade", "trading", "contact", "office",
    "enquiry", "enquiries", "inquiry", "inquiries", "marketing", "business",
    "bd", "purchase", "purchasing", "buy", "buyer", "procurement", "import",
    "imports", "admin", "service", "support", "hello", "mail", "email",
    "company", "general", "overseas", "international", "foreigntrade",
    "sale", "market", "customer", "cs", "help", "order", "orders",
})

EMAIL_KIND_ROLE = "role"
EMAIL_KIND_PERSONAL = "personal"


@dataclass
class LeadEmail:
    """Один почтовый адрес компании."""

    email: str                       # нормализован в нижний регистр
    kind: str = EMAIL_KIND_ROLE      # role | personal
    source_url: str = ""             # страница, с которой адрес снят
    first_seen: datetime = field(default_factory=utcnow)
    last_seen: datetime = field(default_factory=utcnow)

    @property
    def local_part(self) -> str:
        return self.email.split("@", 1)[0] if "@" in self.email else self.email

    @property
    def domain(self) -> str:
        return self.email.split("@", 1)[1] if "@" in self.email else ""

    @property
    def is_role(self) -> bool:
        return self.kind == EMAIL_KIND_ROLE

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["first_seen"] = self.first_seen.isoformat()
        data["last_seen"] = self.last_seen.isoformat()
        return data


@dataclass
class LeadCompany:
    """Карточка компании-импортёра."""

    company_name_en: str = ""
    company_name_zh: str = ""
    province: str = ""
    city: str = ""
    website: str = ""                # нормализованный https://domain
    domain: str = ""                 # нормализованный домен — ключ дедупликации
    emails: list[LeadEmail] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    wechat: str = ""
    whatsapp: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    profile: str = ""                # какой профиль сработал
    industry_guess: str = ""
    source_url: str = ""
    source_name: str = ""
    first_seen: datetime = field(default_factory=utcnow)
    last_seen: datetime = field(default_factory=utcnow)
    # Служебное: заполняется при enrich, не экспортируется
    enrich_status: str = "pending"   # pending | done | skipped_robots | blocked | no_site
    enrich_note: str = ""

    @property
    def display_name(self) -> str:
        """Имя для CSV: английское, иначе китайское, иначе домен."""
        return self.company_name_en or self.company_name_zh or self.domain

    @property
    def role_emails(self) -> list[LeadEmail]:
        return [e for e in self.emails if e.is_role]

    @property
    def personal_emails(self) -> list[LeadEmail]:
        return [e for e in self.emails if not e.is_role]

    def add_emails(self, found: list[LeadEmail]) -> int:
        """Добавить адреса, пропуская уже известные. Возвращает число новых."""
        known = {e.email for e in self.emails}
        added = 0
        for item in found:
            if item.email in known:
                # Уже знаем — обновляем last_seen, source_url не трогаем.
                for existing in self.emails:
                    if existing.email == item.email:
                        existing.last_seen = item.last_seen
                        break
                continue
            known.add(item.email)
            self.emails.append(item)
            added += 1
        return added

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_name_en": self.company_name_en,
            "company_name_zh": self.company_name_zh,
            "province": self.province,
            "city": self.city,
            "website": self.website,
            "domain": self.domain,
            "phones": list(self.phones),
            "wechat": self.wechat,
            "whatsapp": self.whatsapp,
            "matched_keywords": list(self.matched_keywords),
            "profile": self.profile,
            "industry_guess": self.industry_guess,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "enrich_status": self.enrich_status,
            "enrich_note": self.enrich_note,
        }


__all__ = [
    "LeadCompany",
    "LeadEmail",
    "ROLE_LOCAL_PARTS",
    "EMAIL_KIND_ROLE",
    "EMAIL_KIND_PERSONAL",
    "utcnow",
]
