"""Скоринг «теплоты» лида: cold / warm / hot.

Детерминированная оценка по доступным сигналам контакта и соответствия нише/гео.
Нужна, чтобы приоритизировать рассылку и чтобы агент в CRM сам доводил
холодные/тёплые лиды до горячих.

Оценка прозрачна (без ML): сумма баллов за сигналы, пороги на теплоту.
Никакой нейросети — только проверяемые факты из карточки компании.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from leads.models import LeadCompany

HEAT_COLD = "cold"
HEAT_WARM = "warm"
HEAT_HOT = "hot"

# Веса сигналов.
WEIGHT_ROLE_EMAIL = 40
WEIGHT_PERSONAL_EMAIL = 20
WEIGHT_PHONE = 15
WEIGHT_MESSENGER = 15
WEIGHT_WEBSITE = 5
WEIGHT_NICHE_MATCH = 20
WEIGHT_GEO_MATCH = 15
WEIGHT_ACTIVITY = 10
WEIGHT_INDUSTRY = 5

# Пороги теплоты.
HOT_THRESHOLD = 60
WARM_THRESHOLD = 30

# Максимально возможный балл (для документирования).
MAX_SCORE = (
    WEIGHT_ROLE_EMAIL
    + WEIGHT_PHONE
    + WEIGHT_MESSENGER
    + WEIGHT_WEBSITE
    + WEIGHT_NICHE_MATCH
    + WEIGHT_GEO_MATCH
    + WEIGHT_ACTIVITY
    + WEIGHT_INDUSTRY
)

# Псевдонимы стран — приводим к каноническому английскому имени.
_COUNTRY_ALIASES = {
    "russia": "russia",
    "россия": "russia",
    "российская федерация": "russia",
    "rf": "russia",
    "kazakhstan": "kazakhstan",
    "казахстан": "kazakhstan",
    "kz": "kazakhstan",
    "china": "china",
    "китай": "china",
    "中国": "china",
    "prc": "china",
    "turkey": "turkey",
    "турция": "turkey",
    "türkiye": "turkey",
}


@dataclass
class LeadHeat:
    """Оценка теплоты одного лида."""

    heat: str                # cold | warm | hot
    score: int
    reasons: list[str] = field(default_factory=list)

    @property
    def is_hot(self) -> bool:
        return self.heat == HEAT_HOT

    @property
    def is_warm(self) -> bool:
        return self.heat == HEAT_WARM

    @property
    def is_cold(self) -> bool:
        return self.heat == HEAT_COLD


def canonical_country(country: str) -> str:
    """Каноническое английское имя страны (``russia``/``kazakhstan``/…)."""
    return _COUNTRY_ALIASES.get((country or "").strip().lower(), (country or "").strip().lower())


def country_matches(country: str, target: set[str]) -> bool:
    """Входит ли страна компании в целевой набор (с учётом псевдонимов)."""
    if not target or not country:
        return False
    return canonical_country(country) in {canonical_country(c) for c in target}


def heat_from_score(score: int) -> str:
    """Теплота по баллу: hot / warm / cold."""
    if score >= HOT_THRESHOLD:
        return HEAT_HOT
    if score >= WARM_THRESHOLD:
        return HEAT_WARM
    return HEAT_COLD


def score_heat(company: LeadCompany, *, countries: set[str] | None = None) -> LeadHeat:
    """Посчитать теплоту лида по сигналам его карточки.

    Args:
        company: Карточка компании (после обогащения).
        countries: Целевые страны кампании — дают бонус за гео-совпадение.
            ``None`` или пустое множество — бонус не начисляется.

    Returns:
        :class:`LeadHeat` с теплотой, баллом и списком сработавших сигналов.
    """
    score = 0
    reasons: list[str] = []

    if company.role_emails:
        score += WEIGHT_ROLE_EMAIL
        reasons.append("role_email")
    if company.personal_emails:
        score += WEIGHT_PERSONAL_EMAIL
        reasons.append("personal_email")
    if company.phones:
        score += WEIGHT_PHONE
        reasons.append("phone")
    if company.wechat or company.whatsapp:
        score += WEIGHT_MESSENGER
        reasons.append("messenger")
    if company.website:
        score += WEIGHT_WEBSITE
        reasons.append("website")
    if company.matched_keywords:
        score += WEIGHT_NICHE_MATCH
        reasons.append("niche_match")
    if country_matches(company.country, countries or set()):
        score += WEIGHT_GEO_MATCH
        reasons.append("geo_match")
    if company.offers or company.requests:
        score += WEIGHT_ACTIVITY
        reasons.append("activity")
    if company.industry_guess:
        score += WEIGHT_INDUSTRY
        reasons.append("industry")

    return LeadHeat(heat=heat_from_score(score), score=score, reasons=reasons)


def heat_breakdown(companies: list[LeadCompany], *, countries: set[str] | None = None) -> dict[str, int]:
    """Число лидов по теплоте: ``{cold: n, warm: n, hot: n}``."""
    counts = {HEAT_COLD: 0, HEAT_WARM: 0, HEAT_HOT: 0}
    for company in companies:
        counts[score_heat(company, countries=countries).heat] += 1
    return counts


__all__ = [
    "HEAT_COLD",
    "HEAT_HOT",
    "HEAT_WARM",
    "HOT_THRESHOLD",
    "MAX_SCORE",
    "WARM_THRESHOLD",
    "LeadHeat",
    "canonical_country",
    "country_matches",
    "heat_breakdown",
    "heat_from_score",
    "score_heat",
]
