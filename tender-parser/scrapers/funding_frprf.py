"""Скрапер Фонда развития промышленности (frprf.ru).

ФРП предоставляет льготные займы производственным предприятиям по ставкам 1-5%.
Сайт: https://frprf.ru
"""

from __future__ import annotations

import logging
from typing import Any

from scrapers.funding_base import FundingBaseScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://frprf.ru"


class FrprfScraper(FundingBaseScraper):
    """Парсер программ Фонда развития промышленности."""

    source_platform = "frprf"

    _STATIC_PROGRAMS: list[dict[str, Any]] = [
        {
            "external_id": "frp-stanki",
            "program_name": "Программа «Станки»",
            "program_type": "loan",
            "organizer_name": "Фонд развития промышленности",
            "organizer_url": "https://frprf.ru/zaymy/stanki/",
            "amount_min": 5_000_000,
            "amount_max": 500_000_000,
            "rate": 1.0,
            "term_months": 60,
            "regions": [],
            "industries": ["Станкостроение", "Машиностроение", "Промышленность"],
            "description": (
                "Льготные займы 1% годовых на приобретение и создание металлообрабатывающих "
                "станков и оборудования. Финансирует разработку и серийный выпуск "
                "отечественных станков. Возможно частичное освобождение от уплаты суммы займа."
            ),
            "requirements": (
                "Российское юрлицо. Проект в сфере станкостроения и инструментального "
                "производства. Собственное финансирование не менее 15% стоимости проекта. "
                "Минимальный оборот — 600 млн руб. в год."
            ),
            "target_audience": "industry",
            "status": "active",
            "original_url": "https://frprf.ru/zaymy/stanki/",
        },
        {
            "external_id": "frp-komponent",
            "program_name": "Программа «Комплектующие изделия»",
            "program_type": "loan",
            "organizer_name": "Фонд развития промышленности",
            "organizer_url": "https://frprf.ru/zaymy/komplektuyushchie-izdeliya/",
            "amount_min": 5_000_000,
            "amount_max": 200_000_000,
            "rate": 3.0,
            "term_months": 60,
            "regions": [],
            "industries": ["Электроника", "Машиностроение", "Промышленность"],
            "description": (
                "Займы 3% годовых на создание производства критических "
                "комплектующих изделий, замещающих импортные компоненты. "
                "Поддержка локализации производства компонентной базы."
            ),
            "requirements": (
                "Российское юрлицо. Проект по выпуску комплектующих, включённых "
                "в перечень критической продукции. Доля собственного финансирования "
                "не менее 10%."
            ),
            "target_audience": "industry",
            "status": "active",
            "original_url": "https://frprf.ru/zaymy/komplektuyushchie-izdeliya/",
        },
        {
            "external_id": "frp-cifra",
            "program_name": "Программа «Цифровизация промышленности»",
            "program_type": "loan",
            "organizer_name": "Фонд развития промышленности",
            "organizer_url": "https://frprf.ru/zaymy/tsifrovizatsiya-promyshlennosti/",
            "amount_min": 10_000_000,
            "amount_max": 500_000_000,
            "rate": 1.0,
            "term_months": 60,
            "regions": [],
            "industries": ["IT", "Промышленность", "Цифровизация"],
            "description": (
                "Займы 1% годовых на внедрение отечественного программного обеспечения "
                "и промышленных цифровых решений. Субсидирование расходов "
                "на цифровую трансформацию производственных процессов."
            ),
            "requirements": (
                "Промышленное предприятие или IT-компания. Приобретение исключительно "
                "российского ПО из реестра Минцифры. Выручка не менее 500 млн руб."
            ),
            "target_audience": "industry",
            "status": "active",
            "original_url": "https://frprf.ru/zaymy/tsifrovizatsiya-promyshlennosti/",
        },
        {
            "external_id": "frp-ecodesign",
            "program_name": "Программа «Повышение производительности»",
            "program_type": "loan",
            "organizer_name": "Фонд развития промышленности",
            "organizer_url": "https://frprf.ru/zaymy/povyshenie-proizvoditelnosti/",
            "amount_min": 5_000_000,
            "amount_max": 300_000_000,
            "rate": 3.0,
            "term_months": 60,
            "regions": [],
            "industries": ["Промышленность"],
            "description": (
                "Займы 3% годовых на модернизацию производства и внедрение "
                "передовых технологий. Цель — рост производительности труда "
                "не менее чем на 30% в течение 3 лет с момента выдачи займа."
            ),
            "requirements": (
                "Промышленное предприятие. Наличие конкретной программы повышения "
                "производительности. Объём выручки не менее 300 млн руб."
            ),
            "target_audience": "industry",
            "status": "active",
            "original_url": "https://frprf.ru/zaymy/povyshenie-proizvoditelnosti/",
        },
        {
            "external_id": "frp-startup",
            "program_name": "Программа «Стартап-Прогресс»",
            "program_type": "loan",
            "organizer_name": "Фонд развития промышленности",
            "organizer_url": "https://frprf.ru/zaymy/startap-progress/",
            "amount_min": 5_000_000,
            "amount_max": 100_000_000,
            "rate": 3.0,
            "term_months": 60,
            "regions": [],
            "industries": ["Промышленность", "Инновации"],
            "description": (
                "Займы 3% для малых промышленных предприятий (выручка менее 1 млрд руб.) "
                "на запуск нового производства или расширение действующего. "
                "Специальный трек для компаний до 3 лет."
            ),
            "requirements": (
                "ООО или АО с выручкой до 1 млрд руб. Производственная деятельность "
                "согласно ОКВЭД. Наличие бизнес-плана. Доля собственного финансирования "
                "не менее 20%."
            ),
            "target_audience": "startup",
            "status": "active",
            "original_url": "https://frprf.ru/zaymy/startap-progress/",
        },
    ]

    def parse_programs(self) -> list[dict[str, Any]]:
        programs = []
        for item in self._STATIC_PROGRAMS:
            programs.append(self._make_program(**item))  # type: ignore[arg-type]

        try:
            programs.extend(self._fetch_live())
        except Exception as e:
            logger.warning("frprf live fetch failed: %s", e)
        return programs

    def _fetch_live(self) -> list[dict[str, Any]]:
        """Парсинг актуального списка займов с frprf.ru."""
        html = self.fetch("https://frprf.ru/zaymy/")
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        programs = []

        for card in soup.select(".program-item, .loan-card, .product-card")[:8]:
            title_el = card.select_one("h2, h3, .program-title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"):
                href = _BASE_URL + href
            if not title or not href:
                continue

            programs.append(
                self._make_program(
                    external_id=f"live-frp-{hash(href) % 100000}",
                    program_name=title,
                    program_type="loan",
                    organizer_name="Фонд развития промышленности",
                    organizer_url=href,
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    industries=["Промышленность"],
                    status="active",
                    original_url=href,
                )
            )
        return programs
