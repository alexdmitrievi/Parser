"""Парсер Росэлторг (roseltorg.ru).

Одна из 8 федеральных ЭТП. Крупнейшая по объёму 44-ФЗ.
Парсит HTML-страницу поиска /procedures/search.
Структура: div.search-results__item с вложенными блоками.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from shared.models import TenderCreate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RoseltorgScraper(BaseScraper):
    """Парсер roseltorg.ru — HTML-парсинг страницы поиска."""

    platform = "roseltorg"
    base_url = "https://www.roseltorg.ru"
    min_delay = 3.0
    max_delay = 6.0

    def _parse_price(self, text: str) -> Optional[float]:
        """Извлечь цену из текста (убрать ₽, пробелы, конвертировать)."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        # Может быть два числа (НМЦК и обеспечение) — берём первое
        parts = cleaned.split(".")
        if len(parts) > 2:
            # Формат вида 545916.00 или 545.916.00
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"]:
            try:
                return datetime.strptime(s.strip()[:19], fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        """Парсит HTML страницы поиска Росэлторга."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        items = soup.select("div.search-results__item")
        for item in items:
            data = {}

            # Заголовок (предмет закупки)
            subject = item.select_one(".search-results__subject")
            if not subject:
                continue
            link = subject.find("a")
            if link:
                data["title"] = link.get_text(strip=True)
                href = link.get("href", "")
                data["url"] = self.base_url + href if href.startswith("/") else href
                # Номер реестра из href: /procedure/0373200583226000006
                num_match = re.search(r"/procedure/(\d+)", href)
                if num_match:
                    data["registry_number"] = num_match.group(1)
            else:
                data["title"] = subject.get_text(strip=True)

            if not data.get("title") or len(data["title"]) < 5:
                continue

            # Номер и тип закупки из .search-results__header
            header = item.select_one(".search-results__header")
            if header:
                lot = item.select_one(".search-results__lot")
                if lot:
                    lot_link = lot.find("a")
                    if lot_link and not data.get("registry_number"):
                        num_match = re.search(r"(\d{10,})", lot_link.get_text())
                        if num_match:
                            data["registry_number"] = num_match.group(1)

                section = item.select_one(".search-results__section")
                if section:
                    section_text = section.get_text(strip=True).lower()
                    if "44-фз" in section_text:
                        data["law_type"] = "44-fz"
                    elif "223-фз" in section_text:
                        data["law_type"] = "223-fz"
                    else:
                        data["law_type"] = "44-fz"

            # Регион
            region_el = item.select_one(".search-results__region")
            if region_el:
                region_text = region_el.get_text(strip=True)
                # Убираем код региона "77. г. Москва" → "г. Москва"
                region_text = re.sub(r"^\d+\.\s*", "", region_text)
                data["region"] = region_text

            # Заказчик
            customer_el = item.select_one(".search-results__customer")
            if customer_el:
                # Внутри может быть "Организатор" + имя
                tooltip = customer_el.select_one(".search-results__tooltip")
                if tooltip:
                    data["customer"] = tooltip.get_text(strip=True)
                else:
                    cust_link = customer_el.find("a")
                    if cust_link:
                        data["customer"] = cust_link.get_text(strip=True)
                    else:
                        text = customer_el.get_text(strip=True)
                        # Убираем "Организатор" из начала
                        text = re.sub(r"^Организатор\s*", "", text)
                        data["customer"] = text

            # Цена и дедлайн (из блока данных)
            data_block = item.select_one(".search-results__data")
            if data_block:
                data_text = data_block.get_text()
                price_match = re.search(r"([\d\s,.]+)\s*₽", data_text)
                if price_match:
                    data["nmck"] = self._parse_price(price_match.group(1))

                # Дедлайн из <time> или из текста
                time_el = data_block.select_one("time.search-results__time, time")
                if time_el:
                    data["deadline"] = time_el.get_text(strip=True).replace(" в ", " ")
                else:
                    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", data_text)
                    if date_match:
                        data["deadline"] = date_match.group(1)

                # Способ закупки
                method_el = data_block.select_one("p.search-results__type")
                if method_el:
                    method_text = method_el.get_text(strip=True).lower()
                    if "аукцион" in method_text:
                        data["purchase_method"] = "AE"
                    elif "конкурс" in method_text:
                        data["purchase_method"] = "OK"
                    elif "котиров" in method_text or "запрос цен" in method_text:
                        data["purchase_method"] = "ZK"
                    elif "предложен" in method_text:
                        data["purchase_method"] = "ZP"

            results.append(data)

        return results

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type=item.get("law_type", "44-fz"),
                purchase_method=item.get("purchase_method"),
                title=item["title"],
                customer_name=item.get("customer"),
                customer_region=item.get("region"),
                nmck=item.get("nmck"),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 3, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                "ремонт", "капитальный ремонт", "строительные работы",
                "поставка оборудования", "поставка мебели",
                "IT услуги", "техническое обслуживание",
                "уборка", "клининг", "охрана",
                "продукты питания", "медицинское оборудование",
                "транспортные услуги", "проектные работы",
                "электромонтажные работы", "благоустройство",
                "канцтовары", "спецодежда", "лекарственные средства",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[Roseltorg] Searching: {query}")
                for page in range(1, max_pages + 1):
                    url = f"{self.base_url}/procedures/search?{urlencode({'text': query, 'page': str(page)})}"
                    try:
                        resp = self.fetch(url)
                        items = self._parse_page(resp.text)
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error: {e}")
                        break

        logger.info(f"[Roseltorg] Total: {len(all_tenders)} tenders")
        return all_tenders
