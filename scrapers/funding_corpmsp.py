"""Скрапер Корпорации МСП (corpmsp.ru) — федеральная поддержка МСП.

Парсит страницу с мерами поддержки, льготными кредитами и инструментами
гарантийной поддержки для малого и среднего предпринимательства.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.funding_base import FundingBaseScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://corpmsp.ru"


class CorpMspScraper(FundingBaseScraper):
    """Парсер программ Корпорации МСП."""

    source_platform = "corpmsp"

    # Фиксированные программы: обновляются вручную при смене условий на сайте.
    # Источник: corpmsp.ru/services/ (проверено 2025-2026)
    _STATIC_PROGRAMS: list[dict[str, Any]] = [
        {
            "external_id": "prog-1764",
            "program_name": "Льготное кредитование МСП (Программа 1764)",
            "program_type": "loan",
            "organizer_name": "Корпорация МСП / Банк России",
            "organizer_url": "https://corpmsp.ru/services/subsidizirovaniye-kreditov/",
            "amount_min": 500_000,
            "amount_max": 2_000_000_000,
            "rate": 8.5,
            "term_months": 120,
            "regions": [],
            "industries": [],
            "description": (
                "Льготные кредиты для субъектов МСП по ставке до 8,5% годовых. "
                "Кредиты предоставляются банками — партнёрами программы. "
                "Инвестиционные кредиты: до 2 млрд руб. на 10 лет. "
                "Оборотные кредиты: до 500 млн руб. на 3 года."
            ),
            "requirements": (
                "Субъект МСП (ИП или юрлицо), включённый в реестр МСП. "
                "Деятельность в приоритетных отраслях: IT, туризм, торговля, "
                "обрабатывающая промышленность, АПК, здравоохранение и другие."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://corpmsp.ru/services/subsidizirovaniye-kreditov/",
        },
        {
            "external_id": "guarantee-msp",
            "program_name": "Гарантийная поддержка МСП",
            "program_type": "guarantee",
            "organizer_name": "Корпорация МСП",
            "organizer_url": "https://corpmsp.ru/services/garantijnaya-podderzhka/",
            "amount_min": None,
            "amount_max": 500_000_000,
            "rate": None,
            "term_months": None,
            "regions": [],
            "industries": [],
            "description": (
                "Гарантии и поручительства по кредитам для МСП, не имеющих достаточного "
                "залогового обеспечения. Гарантия покрывает до 70% суммы кредита. "
                "Гарантийный продукт 'Стандарт' и 'Инвестиционный' для разных целей."
            ),
            "requirements": (
                "Субъект МСП, включённый в реестр. Отсутствие задолженности перед бюджетом. "
                "Кредитная история без просрочек более 30 дней за последние 12 месяцев."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://corpmsp.ru/services/garantijnaya-podderzhka/",
        },
        {
            "external_id": "microloan-msp",
            "program_name": "Микрозаймы для МСП и самозанятых",
            "program_type": "microloan",
            "organizer_name": "Корпорация МСП / Региональные МФО",
            "organizer_url": "https://corpmsp.ru/services/mikrozajmy/",
            "amount_min": 100_000,
            "amount_max": 5_000_000,
            "rate": 4.25,
            "term_months": 36,
            "regions": [],
            "industries": [],
            "description": (
                "Микрозаймы для субъектов МСП и самозанятых через региональные "
                "микрофинансовые организации. Ставка от 4,25% для социальных "
                "предпринимателей и инновационных компаний. "
                "Стандартная ставка — до 50% ключевой ставки ЦБ РФ."
            ),
            "requirements": (
                "МСП (включая ИП) и самозанятые. Нет ограничений по отрасли. "
                "Обращение в региональную МФО по месту регистрации бизнеса."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://corpmsp.ru/services/mikrozajmy/",
        },
        {
            "external_id": "leasing-msp",
            "program_name": "Льготный лизинг оборудования",
            "program_type": "leasing",
            "organizer_name": "Корпорация МСП / ГТЛК",
            "organizer_url": "https://corpmsp.ru/services/lizingovaya-podderzhka/",
            "amount_min": 1_000_000,
            "amount_max": 500_000_000,
            "rate": 6.0,
            "term_months": 84,
            "regions": [],
            "industries": ["Промышленность", "Транспорт", "АПК", "Строительство"],
            "description": (
                "Льготный лизинг отечественного оборудования, транспорта, "
                "сельхозтехники и спецтехники для субъектов МСП. "
                "Ставка удорожания от 6% годовых. Первоначальный взнос от 5%."
            ),
            "requirements": (
                "Субъект МСП в реестре. Объект лизинга — новое оборудование "
                "российского производства или перечня приоритетных видов."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://corpmsp.ru/services/lizingovaya-podderzhka/",
        },
    ]

    def parse_programs(self) -> list[dict[str, Any]]:
        """Возвращает программы Корпорации МСП.

        Использует curated-данные + попытка обновить с официального сайта.
        """
        programs = []
        for item in self._STATIC_PROGRAMS:
            programs.append(
                self._make_program(**item)  # type: ignore[arg-type]
            )

        # Попытка получить актуальные новости/программы с сайта
        try:
            programs.extend(self._fetch_live())
        except Exception as e:
            logger.warning("corpmsp live fetch failed: %s", e)

        return programs

    def _fetch_live(self) -> list[dict[str, Any]]:
        """Парсим страницу актуальных мер поддержки с сайта corpmsp.ru."""
        html = self.fetch("https://corpmsp.ru/services/")
        if not html:
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        programs = []

        for card in soup.select(".service-item, .support-card, article.card")[:10]:
            title_el = card.select_one("h2, h3, .card-title, .item-title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .card-text, .item-text")

            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"):
                href = _BASE_URL + href
            desc = desc_el.get_text(strip=True) if desc_el else ""

            if not title or not href:
                continue

            programs.append(
                self._make_program(
                    external_id=f"live-{hash(href) % 100000}",
                    program_name=title,
                    program_type="loan",
                    organizer_name="Корпорация МСП",
                    organizer_url=href,
                    description=desc,
                    status="active",
                    original_url=href,
                )
            )

        return programs
