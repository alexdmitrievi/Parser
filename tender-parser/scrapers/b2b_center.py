"""Парсер B2B-Center (b2b-center.ru).

Крупнейшая коммерческая площадка РФ — ~30% коммерческих тендеров.
Парсит таблицу table.search-results на /market/.
Структура: 5 колонок — Название | Заказчик | Опубликовано | Дедлайн | Избранное.
Цена и регион в списке отсутствуют — только на странице тендера.
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


class B2BCenterScraper(BaseScraper):
    """Парсер b2b-center.ru."""

    platform = "b2b_center"
    base_url = "https://www.b2b-center.ru"
    min_delay = 3.0
    max_delay = 7.0

    SEARCH_URL = "https://www.b2b-center.ru/market/"

    def _build_url(self, query: str, page: int = 1) -> str:
        params = {"query": query, "page": str(page)}
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    def _parse_date(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        text = text.strip()
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Реальная структура: table.search-results > tr (первый — заголовок)
        table = soup.select_one("table.search-results")
        if not table:
            # Fallback: любая таблица с тендерными ссылками
            table = soup.find("table")
        if not table:
            return results

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            item = {}

            # Колонка 0: Название + ссылка
            link = cells[0].find("a")
            if link:
                title_text = link.get_text(strip=True)
                if not title_text or len(title_text) < 5:
                    continue
                # Убираем префикс "Процедура закупки № 1234567" / "Запрос предложений № 1234567"
                title_text = re.sub(
                    r"^(?:Процедура закупки|Запрос предложений|Запрос цен|Запрос котировок|Конкурс|Аукцион)\s*№?\s*\d+/?\.?\s*\d*",
                    "", title_text
                ).strip()
                if not title_text or len(title_text) < 5:
                    title_text = link.get_text(strip=True)  # вернуть оригинал
                item["title"] = title_text
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = self.base_url + href
                item["url"] = href
                # Номер из URL
                num_match = re.search(r"tender-(\d+)", href)
                if num_match:
                    item["registry_number"] = num_match.group(1)
            else:
                continue

            # Колонка 1: Заказчик
            if len(cells) > 1:
                cust_link = cells[1].find("a")
                if cust_link:
                    item["customer"] = cust_link.get_text(strip=True)
                else:
                    item["customer"] = cells[1].get_text(strip=True) or None

            # Колонка 2: Дата публикации
            if len(cells) > 2:
                item["publish_date"] = cells[2].get_text(strip=True)

            # Колонка 3: Дедлайн
            if len(cells) > 3:
                item["deadline"] = cells[3].get_text(strip=True)

            results.append(item)

        return results

    def _parse_detail(self, html: str) -> dict:
        """Извлечь доп. данные с детальной страницы тендера."""
        soup = BeautifulSoup(html, "html.parser")
        detail = {}

        # Парсим таблицу с параметрами (key-value rows)
        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower()
                val = cells[1].get_text(strip=True)
                if not val or len(val) < 2:
                    continue

                if "организатор" in key:
                    detail["customer"] = val[:200]
                elif "стоимость" in key or "цена" in key or "нмцк" in key:
                    price = self._parse_price(val)
                    if price:
                        detail["nmck"] = price
                elif "адрес" in key and ("поставк" in key or "выполнен" in key or "оказан" in key):
                    detail["region"] = val[:200]
                elif "место" in key and "поставк" in key:
                    detail["region"] = val[:200]

        return detail

    def _parse_price(self, text: str) -> Optional[float]:
        if not text or "без указания" in text.lower():
            return None
        cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    def _enrich_tenders(self, tenders: list[TenderCreate], max_enrich: int = 30) -> list[TenderCreate]:
        """Дозагрузить заказчика и регион с детальных страниц (для первых N тендеров)."""
        enriched = 0
        for t in tenders:
            if enriched >= max_enrich:
                break
            if not t.original_url:
                continue
            # Загружаем только если нет заказчика или региона
            if t.customer_name and t.customer_region:
                continue
            try:
                self._delay()
                resp = self.fetch(t.original_url)
                detail = self._parse_detail(resp.text)
                if detail.get("customer") and not t.customer_name:
                    t.customer_name = detail["customer"]
                if detail.get("region") and not t.customer_region:
                    t.customer_region = detail["region"]
                if detail.get("nmck") and not t.nmck:
                    t.nmck = detail["nmck"]
                enriched += 1
                logger.debug(f"  Enriched: {t.registry_number} — customer={t.customer_name is not None}, region={t.customer_region is not None}")
            except Exception as e:
                logger.debug(f"  Enrich failed for {t.registry_number}: {e}")
                continue
        logger.info(f"[B2B-Center] Enriched {enriched} tenders with detail data")
        return tenders

    def parse_tenders(self, raw_items: list[dict]) -> list[TenderCreate]:
        tenders = []
        for item in raw_items:
            tenders.append(TenderCreate(
                source_platform=self.platform,
                registry_number=item.get("registry_number"),
                law_type="commercial",
                purchase_method=None,
                title=item["title"],
                customer_name=item.get("customer"),
                customer_region=None,
                nmck=None,
                publish_date=self._parse_date(item.get("publish_date", "")),
                submission_deadline=self._parse_date(item.get("deadline", "")),
                original_url=item.get("url", ""),
            ))
        return tenders

    def run(self, queries: list[str] | None = None, max_pages: int = 5, **kwargs) -> list[TenderCreate]:
        if queries is None:
            queries = [
                # Поставки
                "поставка оборудования", "поставка материалов", "поставка запчастей",
                "поставка спецодежды", "поставка компьютеров",
                # Ремонт и строительство
                "ремонт", "капитальный ремонт", "строительство",
                "строительно-монтажные работы", "реконструкция",
                # Услуги
                "IT услуги", "транспортные услуги", "логистика",
                "уборка", "клининг", "охрана", "аутсорсинг",
                "техническое обслуживание", "сервисное обслуживание",
                # Товары
                "мебель", "продукты питания", "медицинское оборудование",
                "канцтовары", "химическая продукция", "металлопрокат",
                "электрооборудование", "трубная продукция",
                # Проекты
                "проектные работы", "инженерные изыскания",
            ]

        all_tenders: list[TenderCreate] = []

        with self:
            for query in queries:
                logger.info(f"[B2B-Center] Searching: {query}")

                for page in range(1, max_pages + 1):
                    url = self._build_url(query, page)
                    try:
                        resp = self.fetch(url)
                        items = self._parse_page(resp.text)
                        if not items:
                            break
                        tenders = self.parse_tenders(items)
                        all_tenders.extend(tenders)
                        logger.info(f"  Page {page}: {len(tenders)} tenders")
                    except Exception as e:
                        logger.warning(f"  Error page {page}: {e}")
                        break

        # Дозагрузка заказчика/региона/цены с детальных страниц
        if all_tenders:
            all_tenders = self._enrich_tenders(all_tenders, max_enrich=30)

        logger.info(f"[B2B-Center] Total: {len(all_tenders)} tenders")
        return all_tenders
