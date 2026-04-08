"""Скрапер Центров «Мой Бизнес» (mybusiness.ru).

Центры «Мой Бизнес» — федеральная сеть центров поддержки предпринимательства.
Региональные гранты, субсидии, обучение, консультации, офисы.
Сайт: https://mybusiness.ru
"""

from __future__ import annotations

import logging
from typing import Any

from scrapers.funding_base import FundingBaseScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://mybusiness.ru"


class MyBusinessScraper(FundingBaseScraper):
    """Парсер программ центров Мой Бизнес."""

    source_platform = "mybusiness"

    _STATIC_PROGRAMS: list[dict[str, Any]] = [
        {
            "external_id": "mb-grant-start",
            "program_name": "Грант начинающим предпринимателям",
            "program_type": "grant",
            "organizer_name": "Центры «Мой Бизнес»",
            "organizer_url": "https://mybusiness.ru/services/granty/",
            "amount_min": 100_000,
            "amount_max": 500_000,
            "rate": None,
            "term_months": None,
            "regions": [],
            "industries": [],
            "description": (
                "Безвозвратные гранты до 500 000 руб. для начинающих предпринимателей "
                "на первоначальный капитал, покупку оборудования, аренду помещений. "
                "Выдаётся через региональные центры «Мой Бизнес». "
                "Приоритет — молодёжь до 25 лет, безработные, самозанятые."
            ),
            "requirements": (
                "Регистрация ИП или ООО не ранее чем за 12 месяцев до подачи заявки. "
                "Собственное участие в проекте — не менее 15-25% суммы гранта. "
                "Наличие бизнес-плана. Прохождение обучения в центре «Мой Бизнес»."
            ),
            "target_audience": "startup",
            "status": "active",
            "original_url": "https://mybusiness.ru/services/granty/",
        },
        {
            "external_id": "mb-grant-social",
            "program_name": "Грант социальным предпринимателям",
            "program_type": "grant",
            "organizer_name": "Центры «Мой Бизнес»",
            "organizer_url": "https://mybusiness.ru/services/granty-socialnomu-predprinimatelyu/",
            "amount_min": 100_000,
            "amount_max": 1_000_000,
            "rate": None,
            "term_months": None,
            "regions": [],
            "industries": ["Социальное предпринимательство"],
            "description": (
                "Гранты до 1 000 000 руб. для субъектов социального предпринимательства: "
                "образование, здоровый образ жизни, культура, помощь уязвимым группам. "
                "Дополнительные преференции для предприятий в моногородах и труднодоступных "
                "районах."
            ),
            "requirements": (
                "Субъект МСП или самозанятый. Статус социального предпринимателя "
                "по ФЗ № 209-ФЗ. Наличие бизнес-плана. Подача через портал МСП.РФ "
                "или региональный центр «Мой Бизнес»."
            ),
            "target_audience": "social",
            "status": "active",
            "original_url": "https://mybusiness.ru/services/granty-socialnomu-predprinimatelyu/",
        },
        {
            "external_id": "mb-subsidy-export",
            "program_name": "Субсидия на участие в выставках и сертификацию",
            "program_type": "subsidy",
            "organizer_name": "Центры «Мой Бизнес» / Минэкономразвития",
            "organizer_url": "https://mybusiness.ru/services/subvencii/",
            "amount_min": 50_000,
            "amount_max": 3_000_000,
            "rate": None,
            "term_months": None,
            "regions": [],
            "industries": [],
            "description": (
                "Субсидирование расходов МСП на: участие в российских и международных "
                "выставках, получение патентов и сертификатов, "
                "перевод документации, транспортировку продукции на выставки. "
                "Возмещение до 90% затрат."
            ),
            "requirements": (
                "Субъект МСП в реестре ФНС. Наличие понесённых и документально "
                "подтверждённых расходов не ранее 1 января текущего года."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://mybusiness.ru/services/subvencii/",
        },
        {
            "external_id": "mb-coworking",
            "program_name": "Бесплатные коворкинги и офисы для МСП",
            "program_type": "subsidy",
            "organizer_name": "Центры «Мой Бизнес»",
            "organizer_url": "https://mybusiness.ru/coworking/",
            "amount_min": None,
            "amount_max": None,
            "rate": None,
            "term_months": None,
            "regions": [],
            "industries": [],
            "description": (
                "Бесплатные коворкинги, переговорные комнаты и офисные пространства "
                "в центрах «Мой Бизнес» для субъектов МСП и самозанятых. "
                "Доступны более чем в 80 регионах России."
            ),
            "requirements": (
                "Статус субъекта МСП или самозанятого. "
                "Регистрация на портале МСП.РФ."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://mybusiness.ru/coworking/",
        },
        {
            "external_id": "mb-fund-innovation",
            "program_name": "Грант Фонда содействия инновациям (УМНИК)",
            "program_type": "grant",
            "organizer_name": "Фонд содействия инновациям",
            "organizer_url": "https://fasie.ru/programs/programm-umnik/",
            "amount_min": 500_000,
            "amount_max": 500_000,
            "rate": None,
            "term_months": 24,
            "regions": [],
            "industries": ["IT", "Инновации", "Наука"],
            "description": (
                "Программа УМНИК — грант 500 000 руб. молодым учёным и разработчикам "
                "для проведения НИОКР. Финансирует создание прототипов, "
                "научные исследования с коммерческим потенциалом. "
                "Отбор через конкурсы в 80+ регионах."
            ),
            "requirements": (
                "Возраст от 18 до 30 лет. Российское гражданство. "
                "Наличие инновационного проекта с потенциалом коммерциализации. "
                "Участие в конкурсном отборе."
            ),
            "target_audience": "innovation",
            "status": "active",
            "original_url": "https://fasie.ru/programs/programm-umnik/",
        },
        {
            "external_id": "mb-fund-start",
            "program_name": "Грант Фонда содействия инновациям (СТАРТ)",
            "program_type": "grant",
            "organizer_name": "Фонд содействия инновациям",
            "organizer_url": "https://fasie.ru/programs/programm-start/",
            "amount_min": 3_000_000,
            "amount_max": 10_000_000,
            "rate": None,
            "term_months": 36,
            "regions": [],
            "industries": ["IT", "Инновации", "Наука"],
            "description": (
                "Программа СТАРТ для начинающих инновационных компаний: "
                "3-10 млн руб. на R&D без возврата. "
                "СТАРТ-1 (3 млн) — разработка прототипа. "
                "СТАРТ-2 (до 10 млн) — испытание опытного образца."
            ),
            "requirements": (
                "ООО, зарегистрированное не более 2 лет назад. "
                "Инновационный технологический проект. "
                "Наличие команды с компетенциями в области R&D."
            ),
            "target_audience": "startup",
            "status": "active",
            "original_url": "https://fasie.ru/programs/programm-start/",
        },
    ]

    def parse_programs(self) -> list[dict[str, Any]]:
        programs = []
        for item in self._STATIC_PROGRAMS:
            programs.append(self._make_program(**item))  # type: ignore[arg-type]

        try:
            programs.extend(self._fetch_regional_services())
        except Exception as e:
            logger.warning("mybusiness live fetch failed: %s", e)
        return programs

    def _fetch_regional_services(self) -> list[dict[str, Any]]:
        """Парсинг актуальных сервисов mybusiness.ru."""
        html = self.fetch("https://mybusiness.ru/services/")
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        programs = []
        for card in soup.select(".service-card, .mb-service, .service-item")[:8]:
            title_el = card.select_one("h2, h3, .service-name, .card-title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .description")
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
                    external_id=f"live-mb-{hash(href) % 100000}",
                    program_name=title,
                    program_type="grant",
                    organizer_name="Центры «Мой Бизнес»",
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    status="active",
                    original_url=href,
                )
            )
        return programs
