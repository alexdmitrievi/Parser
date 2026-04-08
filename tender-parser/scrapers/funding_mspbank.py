"""Скрапер МСП Банка (mspbank.ru) — государственный банк для МСП.

МСП Банк — государственный банк поддержки малого и среднего предпринимательства.
Сайт: https://www.mspbank.ru
"""

from __future__ import annotations

import logging
from typing import Any

from scrapers.funding_base import FundingBaseScraper

logger = logging.getLogger(__name__)


class MspBankScraper(FundingBaseScraper):
    """Парсер программ МСП Банка."""

    source_platform = "mspbank"

    _STATIC_PROGRAMS: list[dict[str, Any]] = [
        {
            "external_id": "mspb-credit-invest",
            "program_name": "Инвестиционное кредитование МСП",
            "program_type": "loan",
            "organizer_name": "МСП Банк",
            "organizer_url": "https://www.mspbank.ru/financial-support/credits/",
            "amount_min": 3_000_000,
            "amount_max": 500_000_000,
            "rate": 11.0,
            "term_months": 120,
            "regions": [],
            "industries": [],
            "description": (
                "Инвестиционные кредиты для субъектов МСП на закупку оборудования, "
                "строительство, реконструкцию производственных помещений. "
                "Ставка от 11% годовых. Возможна отсрочка погашения основного долга до 12 мес."
            ),
            "requirements": (
                "Субъект МСП в реестре ФНС. Не менее 1 года фактической деятельности. "
                "Положительная кредитная история. Наличие бизнес-плана для проектов "
                "свыше 50 млн руб."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://www.mspbank.ru/financial-support/credits/",
        },
        {
            "external_id": "mspb-oborot",
            "program_name": "Кредит на пополнение оборотных средств",
            "program_type": "loan",
            "organizer_name": "МСП Банк",
            "organizer_url": "https://www.mspbank.ru/financial-support/working-capital/",
            "amount_min": 500_000,
            "amount_max": 100_000_000,
            "rate": 13.5,
            "term_months": 36,
            "regions": [],
            "industries": [],
            "description": (
                "Кредиты на пополнение оборотных средств для малых и средних предприятий. "
                "Финансирование текущей деятельности, закупки сырья, товаров, "
                "расчётов с контрагентами. Возобновляемая кредитная линия."
            ),
            "requirements": (
                "Субъект МСП. Наличие расчётного счёта. Фактическая деятельность "
                "не менее 6 месяцев."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://www.mspbank.ru/financial-support/working-capital/",
        },
        {
            "external_id": "mspb-guarantee",
            "program_name": "Гарантийный продукт МСП Банка",
            "program_type": "guarantee",
            "organizer_name": "МСП Банк",
            "organizer_url": "https://www.mspbank.ru/financial-support/guarantees/",
            "amount_min": 1_000_000,
            "amount_max": 200_000_000,
            "rate": None,
            "term_months": 84,
            "regions": [],
            "industries": [],
            "description": (
                "Банковские гарантии для МСП при участии в государственных закупках "
                "(44-ФЗ, 223-ФЗ), исполнении контрактов, обеспечении заявок. "
                "Гарантия возврата аванса, исполнения обязательств по контракту."
            ),
            "requirements": (
                "Субъект МСП. Контракт или договор с государственным или "
                "коммерческим заказчиком. Комиссия за гарантию — от 0,5% годовых."
            ),
            "target_audience": "msp",
            "status": "active",
            "original_url": "https://www.mspbank.ru/financial-support/guarantees/",
        },
        {
            "external_id": "mspb-export",
            "program_name": "Финансирование экспортёров",
            "program_type": "loan",
            "organizer_name": "МСП Банк / РЭЦ",
            "organizer_url": "https://www.mspbank.ru/financial-support/export/",
            "amount_min": 1_000_000,
            "amount_max": 300_000_000,
            "rate": 4.5,
            "term_months": 60,
            "regions": [],
            "industries": ["Экспорт"],
            "description": (
                "Льготные кредиты 4,5% для МСП-экспортёров на финансирование "
                "экспортных контрактов, предэкспортное и постэкспортное финансирование. "
                "Совместная программа с Российским экспортным центром."
            ),
            "requirements": (
                "Субъект МСП с действующим или планируемым экспортным контрактом. "
                "Экспорт несырьевых неэнергетических товаров/услуг. "
                "Наличие договора с иностранным партнёром."
            ),
            "target_audience": "export",
            "status": "active",
            "original_url": "https://www.mspbank.ru/financial-support/export/",
        },
    ]

    def parse_programs(self) -> list[dict[str, Any]]:
        programs = []
        for item in self._STATIC_PROGRAMS:
            programs.append(self._make_program(**item))  # type: ignore[arg-type]

        try:
            programs.extend(self._fetch_live())
        except Exception as e:
            logger.warning("mspbank live fetch failed: %s", e)
        return programs

    def _fetch_live(self) -> list[dict[str, Any]]:
        html = self.fetch("https://www.mspbank.ru/financial-support/")
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        programs = []

        for card in soup.select(".product-card, .support-item, .bank-product")[:6]:
            title_el = card.select_one("h2, h3, .product-name")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = link_el["href"] if link_el else ""
            if href and not href.startswith("http"):
                href = "https://www.mspbank.ru" + href
            if not title or not href:
                continue
            programs.append(
                self._make_program(
                    external_id=f"live-mspb-{hash(href) % 100000}",
                    program_name=title,
                    program_type="loan",
                    organizer_name="МСП Банк",
                    description=desc_el.get_text(strip=True) if desc_el else "",
                    status="active",
                    original_url=href,
                )
            )
        return programs
