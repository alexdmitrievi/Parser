"""Fabrikant (fabrikant.ru) source adapter — этап 5, коммерческие площадки.

Жёсткие правила (по ТЗ):
    * только публичные страницы поиска, без обхода авторизации/антибота;
    * robots.txt проверяется перед каждым обходом;
    * консервативный rate-limit.

Fabrikant — Next.js-приложение: часть выдачи рендерится сервером и
парсится обычным HTTP-фетчем; если площадка перестанет отдавать
серверный HTML, адаптер честно вернёт 0 записей (health-трекер пометит
источник деградировавшим) — обходить защиту мы не будем. Если данные
окажутся доступны только по платному API, источник помечается
"requires_subscription" и отключается.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from engine.types import (
    SourceConfig, SourceCategory, FetchMethod, FetchResult, ParsedRecord,
    RateLimitConfig,
)
from engine.sources.base import BaseSourceAdapter
from engine.fetchers.robots import get_robots_checker
from engine.parsers.utils import parse_price, parse_date, clean_text
from engine.config.registry import get_registry
from engine.observability.logger import get_logger

logger = get_logger("source.fabrikant")

_TRADE_LINK = re.compile(r"/trades/[^?#]*\d+")
_SKIP_URLS = re.compile(
    r"/privacy|/policy|/legal|/terms|/politics|/politika|/agreement|/offer"
    r"|/docs/|/faq|/about|/contacts|/reviews|/rules|/regulations",
    re.IGNORECASE,
)
_SKIP_TITLES = re.compile(
    r"политик|персональных данны|конфиденциальност|cookie|куки|оферт"
    r"|пользовательское соглашение|согласие на обработку"
    r"|регламент\s+(?:работы|площадк|систем|взаимодейств)"
    r"|условия\s+(?:использован|работы|площадк|поставк)"
    r"|инструкци[яи]\s+(?:по\s|для\s)"
    r"|положение\s+о\s+"
    r"|документаци[яи]\s+(?:по\s|площадк|торгов)",
    re.IGNORECASE,
)


class FabrikantSourceAdapter(BaseSourceAdapter):
    """HTTP-адаптер публичного поиска fabrikant.ru."""

    # Пустой discover — осознанный пропуск по robots.txt, не сбой источника
    empty_discovery_ok = True

    def discover(self) -> list[str]:
        robots = get_robots_checker()
        urls: list[str] = []
        queries = self.config.search_queries or []
        max_pages = self.config.max_pages or 2

        for query in queries:
            for page in range(1, max_pages + 1):
                params = {"SearchString": query, "page": str(page)}
                url = f"{self.config.base_url}/trades/procedure/search/?{urlencode(params)}"
                if not robots.allowed(url):
                    logger.warning(
                        f"[{self.source_id}] robots.txt disallows {url} — skipping source"
                    )
                    return []
                urls.append(url)
        return urls

    def parse_listing(self, result: FetchResult) -> list[ParsedRecord]:
        soup = BeautifulSoup(result.content, "html.parser")
        records: list[ParsedRecord] = []

        blocks = soup.select("div[data-id], div[data-slot='card'], div[class*='card']")
        if not blocks:
            seen: list = []
            for link in soup.find_all("a", href=lambda h: h and bool(_TRADE_LINK.search(h))):
                parent = link.find_parent("div")
                if parent is not None and parent not in seen:
                    seen.append(parent)
            blocks = seen

        for block in blocks:
            link = block.find("a", href=lambda h: h and bool(_TRADE_LINK.search(h)))
            if not link:
                continue
            title = clean_text(link.get_text())
            if not title or len(title) <= 5 or _SKIP_TITLES.search(title):
                continue
            href = link.get("href", "")
            if href and _SKIP_URLS.search(href):
                continue
            if href and not href.startswith("http"):
                href = self.config.base_url + href

            registry_number = block.get("data-id")
            if not registry_number and href:
                m = re.search(r"(\d+)", href.split("?")[0].rstrip("/").split("/")[-1])
                registry_number = m.group(1) if m else None

            lines = [ln.strip() for ln in block.get_text(separator="\n").split("\n") if ln.strip()]

            nmck = None
            for line in lines:
                m = re.search(r"([\d\s,.]+)\s*(?:₽|руб)", line)
                if m:
                    nmck = parse_price(m.group(1))
                    break

            deadline = None
            for line in lines:
                m = re.search(r"(\d{2}\.\d{2}\.\d{4})", line)
                if m:
                    deadline = parse_date(m.group(1))
                    break

            customer = None
            for line in lines:
                if re.search(r"\b(ООО|АО|ПАО|ГУП|МУП|ГБУ|МБУ|ФГУП|ОАО|ЗАО)\b", line):
                    customer = line[:200]
                    break

            records.append(ParsedRecord(
                source_id=self.config.source_id,
                registry_number=registry_number,
                title=title,
                original_url=href,
                nmck=nmck,
                customer_name=customer,
                submission_deadline=deadline,
                law_type="commercial",
            ))

        return records


FABRIKANT_CONFIG = SourceConfig(
    source_id="fabrikant",
    platform_name="fabrikant",
    category=SourceCategory.TENDERS,
    base_url="https://www.fabrikant.ru",
    fetch_method=FetchMethod.HTTP,
    search_queries=[
        # Профиль «Подряд ПРО»: расчистка/снос/отделка/топливо
        "расчистка территории", "валка деревьев", "снос", "демонтаж",
        "благоустройство", "текущий ремонт", "ремонт помещений",
        "отделочные работы", "печное топливо", "нефтепродукты",
    ],
    max_pages=2,
    rate_limit=RateLimitConfig(min_delay=4.0, max_delay=8.0),
    law_type_default="commercial",
    # Включается только после приёмки этапов 1–4 (COMMERCIAL_SOURCES=1)
    enabled=False,
)


def register_fabrikant() -> None:
    get_registry().register(FABRIKANT_CONFIG, FabrikantSourceAdapter)


def get_fabrikant_adapter() -> FabrikantSourceAdapter:
    return FabrikantSourceAdapter(FABRIKANT_CONFIG)
