"""Парсер Ростендер (rostender.info).

Агрегатор тендеров РФ — собирает закупки с разных площадок.
Отдаёт богатый HTML с article.tender-row.
Поля: название, цена, регион, город, дедлайн, ссылка, номер.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RostenderScraper(BaseScraper):
    """Парсер rostender.info — агрегатор тендеров."""

    platform = "rostender"
    base_url = "https://rostender.info"
    min_delay = 3.0
    max_delay = 6.0

    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        s = s.strip()[:19]
        for fmt in ["%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        articles = soup.select("article.tender-row")
        for article in articles:
            item = {}

            # Название и ссылка
            link = article.select_one("a.tender-info__description, a.tender-info__link")
            if link:
                item["title"] = link.get_text(strip=True)
                href = link.get("href", "")
                if href.startswith("/"):
                    href = self.base_url + href
                item["url"] = href

            if not item.get("title") or len(item["title"]) < 5:
                continue

            # Номер тендера
            num_el = article.select_one("span.tender__number")
            if num_el:
                num_text = num_el.get_text(strip=True)
                num_match = re.search(r"(\d{5,})", num_text)
                if num_match:
                    item["registry_number"] = num_match.group(1)

            # Цена
            price_el = article.select_one("div.starting-price__price, div.starting-price--price")
            if price_el:
                item["nmck"] = self._parse_price(price_el.get_text())

            # Регион
            region_el = article.select_one("a.tender__region-link")
            if region_el:
                item["region"] = region_el.get_text(strip=True)

            # Город (дополнительно)
            addr_el = article.select_one("div.tender-address")
            if addr_el:
                item["city"] = addr_el.get_text(strip=True)

            # Дедлайн
            deadline_el = article.select_one("time.dtend")
            if deadline_el:
                item["deadline"] = deadline_el.get_text(strip=True)

            # Описание
            desc_el = article.select_one("span.description, div.description")
            if desc_el:
                item["description"] = desc_el.get_text(strip=True)[:500]

            results.append(item)

        return results

    def _detect_law_type(self, title: str, desc: str = "") -> str:
        """Определить тип закупки по тексту."""
        text = (title + " " + desc).lower()
        if "44-фз" in text or "44 фз" in text:
            return "44-fz"
        if "223-фз" in text or "223 фз" in text:
            return "223-fz"
        if "коммерч" in text:
            return "commercial"
        return "commercial"

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            title = item.get("title", "")
            desc = item.get("description", "")
            region = item.get("region", "")
            if item.get("city") and region:
                region = f"{item['city']}, {region}"
            elif item.get("city"):
                region = item["city"]

            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type=self._detect_law_type(title, desc),
                title=title,
                description=desc or None,
                customer_name=None,
                customer_region=region or None,
                nmck=item.get("nmck"),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 5, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                # Строительство
                "ремонт", "капитальный ремонт", "строительство",
                "строительно-монтажные работы", "реконструкция", "благоустройство",
                "кровельные работы", "фасадные работы", "дорожные работы",
                # ГСМ и топливо
                "мазут", "печное топливо", "дизельное топливо", "ГСМ",
                "нефтепродукты", "уголь",
                # Поставки
                "поставка оборудования", "мебель", "спецодежда",
                "электрооборудование", "металлопрокат",
                # Услуги
                "IT услуги", "транспортные услуги", "охрана", "клининг",
                "техническое обслуживание", "проектные работы",
                # Товары
                "продукты питания", "медицинское оборудование", "канцтовары",
                # Прочее
                "вывоз мусора", "утилизация", "озеленение", "спецтехника",
                "страхование", "аудит",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[Rostender] Searching: {query}")
                for page in range(1, max_pages + 1):
                    url = f"{self.base_url}/extsearch?text={query}&page={page}"
                    try:
                        resp = self.fetch(url)
                        items = self._parse_page(resp.text)
                        if not items:
                            logger.info(f"  Page {page}: no results, stopping")
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[Rostender] Total: {len(all_tenders)} tenders")
        return all_tenders
