"""Заготовка адаптера платных источников таможенных данных.

Volza / ImportGenius / Panjiva продают доступ к декларациям по кодам ТН ВЭД —
это самый качественный источник импортёров, но подписка платная и у каждого
провайдера своя схема ответа.

Здесь реализован интерфейс и заглушка:

* без ``LEADS_CUSTOMS_API_KEY`` адаптер сообщает «требует подписки» и
  пропускается без ошибки — прогон продолжается остальными источниками;
* с ключом запрашивается настроенный ``LEADS_CUSTOMS_API_BASE_URL``, ответ
  разбирается маппером выбранного провайдера.

Мапперы (:data:`PROVIDER_FIELD_MAPS`) описаны декларативно: подключение
конкретной подписки — это правка карты полей под её реальный ответ, а не
переписывание адаптера. Ни одна из карт **не проверена на живом API** — у
проекта нет подписки; сверьте имена полей с документацией провайдера.
"""

from __future__ import annotations

import json
from typing import Any

from engine.fetchers.polite_fetcher import PoliteResponse
from engine.sources.leads.base import LeadsSourceAdapter, SourceUnavailable
from engine.types import FetchMethod, RateLimitConfig, RetryConfig, SourceCategory, SourceConfig
from leads.models import LeadCompany, utcnow
from leads.normalizer import (
    is_company_domain,
    normalize_domain,
    normalize_website,
    parse_location,
    split_name_by_script,
)

SOURCE_ID = "customs_api"

SUPPORTED_PROVIDERS = ("volza", "importgenius", "panjiva")

# Как назвать поля ответа провайдера в терминах LeadCompany.
# Значение — цепочка возможных имён; берётся первое непустое.
PROVIDER_FIELD_MAPS: dict[str, dict[str, tuple[str, ...]]] = {
    "volza": {
        "records": ("data", "records", "results"),
        "name": ("buyerName", "buyer", "importerName", "companyName"),
        "name_zh": ("buyerNameLocal", "buyerNameCn"),
        "address": ("buyerAddress", "address", "buyerCity"),
        "website": ("buyerWebsite", "website"),
        "hs_code": ("hsCode", "hs_code"),
    },
    "importgenius": {
        "records": ("shipments", "data", "results"),
        "name": ("consignee_name", "consignee", "company_name"),
        "name_zh": ("consignee_name_local",),
        "address": ("consignee_address", "address"),
        "website": ("website",),
        "hs_code": ("hs_code", "hscode"),
    },
    "panjiva": {
        "records": ("results", "data", "shipments"),
        "name": ("consigneeName", "buyerName", "companyName"),
        "name_zh": ("consigneeNameLocal",),
        "address": ("consigneeAddress", "address"),
        "website": ("website", "companyWebsite"),
        "hs_code": ("hsCode", "hs"),
    },
}


def _first_value(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Первое непустое строковое значение из перечисленных ключей."""
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return str(value).strip()
    return ""


class CustomsApiAdapter(LeadsSourceAdapter):
    """Импортёры по кодам ТН ВЭД из платного источника таможенных данных."""

    def __init__(
        self,
        *args,
        api_key: str = "",
        provider: str = "",
        base_url: str = "",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        from shared.config import (
            leads_customs_api_base_url,
            leads_customs_api_key,
            leads_customs_api_provider,
        )

        self.api_key = api_key or leads_customs_api_key()
        self.provider = (provider or leads_customs_api_provider()).lower()
        self.base_url = (base_url or leads_customs_api_base_url()).rstrip("/")

    # ── доступность ──

    def availability(self) -> tuple[bool, str]:
        """Адаптер работает только при настроенной подписке."""
        if not self.api_key:
            return False, (
                "требует подписки: задайте LEADS_CUSTOMS_API_KEY "
                f"(провайдер {self.provider or 'не выбран'})"
            )
        if self.provider not in SUPPORTED_PROVIDERS:
            return False, (
                f"неизвестный провайдер '{self.provider}'; "
                f"поддерживаются: {', '.join(SUPPORTED_PROVIDERS)}"
            )
        if not self.base_url:
            return False, "не задан LEADS_CUSTOMS_API_BASE_URL для выбранной подписки"
        return True, ""

    @property
    def requires_subscription(self) -> bool:
        """True, когда адаптер пропускается из-за отсутствия подписки."""
        return not self.availability()[0]

    # ── обход ──

    def discover(self) -> list[str]:
        """Запросы по кодам ТН ВЭД из профиля."""
        self.ensure_available()

        hs_codes = list(self.profile.hs_codes) if self.profile else []
        if not hs_codes:
            self._log.warning("У профиля нет hs_codes — запрашивать нечего")
            return []

        max_pages = min(self.limits.max_pages_per_query, self.config.max_pages or 1)
        return [
            f"{self.base_url}?hs_code={code}&country=CN&page={page}"
            for code in hs_codes
            for page in range(1, max_pages + 1)
        ]

    def fetch_page(self, url: str) -> PoliteResponse:
        """Запрос к API с ключом подписки.

        robots.txt к платному API по ключу не применяется: это не обход
        публичного сайта, а вызов оплаченного интерфейса по договору.
        """
        return self._polite.fetch(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
        )

    def parse_companies(self, response: PoliteResponse) -> list[LeadCompany]:
        """Разобрать JSON-ответ провайдера в карточки компаний."""
        field_map = PROVIDER_FIELD_MAPS.get(self.provider)
        if not field_map:
            self._log.warning(f"Нет карты полей для провайдера '{self.provider}'")
            return []

        try:
            payload = json.loads(response.text)
        except (json.JSONDecodeError, TypeError) as e:
            self._log.parse_fail(response.url, f"невалидный JSON: {e}")
            return []

        records = self._records(payload, field_map["records"])
        companies: list[LeadCompany] = []
        now = utcnow()

        for record in records:
            if not isinstance(record, dict):
                continue

            raw_name = _first_value(record, field_map["name"])
            if not raw_name:
                continue

            name_en, name_zh = split_name_by_script(raw_name)
            name_zh = name_zh or _first_value(record, field_map["name_zh"])

            address = _first_value(record, field_map["address"])
            province, city = parse_location(address or raw_name)

            domain = normalize_domain(_first_value(record, field_map["website"]))
            if domain and not is_company_domain(domain):
                domain = ""

            hs_code = _first_value(record, field_map["hs_code"])
            matched = [hs_code] if hs_code else []
            if self.profile:
                matched.extend(self.profile.match(f"{raw_name} {address}"))

            companies.append(
                LeadCompany(
                    company_name_en=name_en,
                    company_name_zh=name_zh,
                    province=province,
                    city=city,
                    website=normalize_website(domain) if domain else "",
                    domain=domain,
                    matched_keywords=list(dict.fromkeys(matched)),
                    profile=self.profile.name if self.profile else "",
                    industry_guess=(
                        self.profile.guess_industry(f"{raw_name} {address}") if self.profile else ""
                    ),
                    source_url=response.url,
                    source_name=SOURCE_ID,
                    first_seen=now,
                    last_seen=now,
                    enrich_status="pending" if domain else "no_site",
                )
            )

        return companies

    @staticmethod
    def _records(payload: Any, keys: tuple[str, ...]) -> list[Any]:
        """Достать список записей из ответа любой из известных форм."""
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []


# ── Конфиг и регистрация ──

CUSTOMS_API_CONFIG = SourceConfig(
    source_id=SOURCE_ID,
    platform_name="customs-api",
    category=SourceCategory.LEADS,
    base_url="",
    fetch_method=FetchMethod.API_JSON,
    max_pages=10,
    rate_limit=RateLimitConfig(min_delay=1.0, max_delay=2.0, max_concurrent=1),
    retry=RetryConfig(max_attempts=3),
    use_proxy=False,
    enabled=True,
)


def register_customs_api() -> None:
    from engine.config.registry import get_registry

    get_registry().register(CUSTOMS_API_CONFIG, CustomsApiAdapter)


def get_customs_api_adapter(profile=None, limits=None, **kwargs) -> CustomsApiAdapter:
    return CustomsApiAdapter(CUSTOMS_API_CONFIG, profile=profile, limits=limits, **kwargs)


__all__ = [
    "CustomsApiAdapter",
    "CUSTOMS_API_CONFIG",
    "register_customs_api",
    "get_customs_api_adapter",
    "SourceUnavailable",
    "SUPPORTED_PROVIDERS",
    "PROVIDER_FIELD_MAPS",
    "SOURCE_ID",
]
