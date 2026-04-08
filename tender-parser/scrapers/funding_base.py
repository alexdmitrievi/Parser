"""Базовый класс для скраперов программ финансирования МСП."""

from __future__ import annotations

import logging
from typing import Any

from scrapers.base import BaseScraper
from shared.models import TenderCreate

logger = logging.getLogger(__name__)

# Типы программ финансирования
PROGRAM_TYPES = {
    "grant": "Грант",
    "loan": "Льготный кредит",
    "microloan": "Микрозайм",
    "subsidy": "Субсидия",
    "guarantee": "Поручительство",
    "compensation": "Компенсация затрат",
    "leasing": "Льготный лизинг",
}

# Целевые аудитории
TARGET_AUDIENCES = {
    "msp": "МСП",
    "ip": "ИП",
    "startup": "Стартапы",
    "self_employed": "Самозанятые",
    "social": "Социальное предпринимательство",
    "export": "Экспортёры",
    "agro": "АПК",
    "industry": "Промышленность",
    "it": "IT",
    "innovation": "Инновации",
}


class FundingBaseScraper(BaseScraper):
    """Базовый скрапер программ поддержки МСП.

    Дочерние классы реализуют parse_programs() и run().
    """

    source_platform: str = "unknown"

    def _make_program(
        self,
        *,
        external_id: str | None = None,
        program_name: str,
        program_type: str,
        organizer_name: str = "",
        organizer_url: str = "",
        amount_min: float | None = None,
        amount_max: float | None = None,
        rate: float | None = None,
        term_months: int | None = None,
        regions: list[str] | None = None,
        industries: list[str] | None = None,
        description: str = "",
        requirements: str = "",
        target_audience: str = "",
        deadline: str | None = None,
        status: str = "active",
        original_url: str = "",
        publish_date: str | None = None,
    ) -> dict[str, Any]:
        """Собрать словарь программы в формате для upsert в БД."""
        return {
            "source_platform": self.source_platform,
            "external_id": external_id,
            "program_name": program_name,
            "program_type": program_type,
            "organizer_name": organizer_name,
            "organizer_url": organizer_url,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "rate": rate,
            "term_months": term_months,
            "regions": regions or [],
            "industries": industries or [],
            "description": description,
            "requirements": requirements,
            "target_audience": target_audience,
            "deadline": deadline,
            "status": status,
            "original_url": original_url,
            "publish_date": publish_date,
        }

    def parse_tenders(self, raw_data: Any = None) -> list[TenderCreate]:
        """Заглушка — финансовые скраперы не возвращают тендеры."""
        return []

    def parse_programs(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def run(self, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            programs = self.parse_programs()
            logger.info("%s: parsed %d programs", self.source_platform, len(programs))
            return programs
        except Exception:
            logger.exception("%s: run failed", self.source_platform)
            return []
