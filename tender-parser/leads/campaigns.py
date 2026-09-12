"""Слой кампаний лидогенерации: ниша + гео + язык под конкретного заказчика.

Кампания — самодостаточный конфиг «лидогенерация как сервис»: одна кампания
соответствует одному запросу заказчика (ниша × гео). Из кампании генерируются:

* :class:`~leads.profiles.Profile` — чтобы работали скоринг (бонусы за нишу
  и гео) и каталоги-адаптеры (ключевые слова, HS-коды);
* цели 2ГИС (:class:`~leads.gis2.Gis2Target`) — рубрика × город из секции
  ``gis2`` кампании.

Файл ``config/lead_campaigns.yaml`` перечитывается при каждом запуске — правки
применяются без изменения кода (как у ``leads_profiles.yaml``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.observability.logger import get_logger
from leads.gis2 import Gis2Target
from leads.profiles import Limits, Profile

logger = get_logger("leads.campaigns")

VALID_LANGUAGES = frozenset({"ru", "en", "zh"})
VALID_DIRECTIONS = frozenset({"import", "export"})

# Домены 2ГИС по странам (для автоподстановки, если в секции gis2 не задан).
GIS2_DOMAINS: dict[str, str] = {"russia": "ru", "kazakhstan": "kz"}


class CampaignError(Exception):
    """Кампания не найдена или конфиг невалиден."""


@dataclass
class Gis2Section:
    """Секция ``gis2`` кампании: города и рубрики для обхода 2ГИС."""

    domain: str = ""                      # домен 2ГИС: ru | kz
    cities: list[str] = field(default_factory=list)   # коды городов (omsk, almaty…)
    rubrics: list[dict[str, str]] = field(default_factory=list)  # {code, name}


@dataclass
class Campaign:
    """Одна кампания лидогенерации: ниша × гео × язык × направление."""

    name: str
    niche_name: str = ""                  # человекочитаемое название ниши
    keywords_en: list[str] = field(default_factory=list)
    keywords_ru: list[str] = field(default_factory=list)
    hs_codes: list[str] = field(default_factory=list)
    target_industries: list[str] = field(default_factory=list)
    direction: str = "import"             # import | export
    language: str = "ru"                  # язык коммуникации с лидами: ru | en | zh
    countries: list[str] = field(default_factory=list)  # целевые страны
    gis2_domain: str = ""
    gis2_cities: list[str] = field(default_factory=list)
    gis2_rubrics: list[dict[str, str]] = field(default_factory=list)

    def to_profile(self) -> Profile:
        """Сгенерировать :class:`~leads.profiles.Profile` из кампании.

        Русские ключевые слова ложатся в ``keywords_zh`` — это слот
        «не-латиница» профиля (матчинг регистронезависимый, иероглифов нет).
        """
        return Profile(
            name=self.name,
            keywords_en=list(self.keywords_en),
            keywords_zh=list(self.keywords_ru),
            hs_codes=list(self.hs_codes),
            target_industries=list(self.target_industries),
            direction=self.direction,
            language=self.language,
            countries=list(self.countries),
        )

    def to_gis2_targets(self) -> list[Gis2Target]:
        """Сгенерировать цели 2ГИС: город × рубрики.

        Страна каждой цели — первая страна кампании; домен 2ГИС берётся из
        секции ``gis2`` (или подставляется по стране).
        """
        if not self.gis2_cities or not self.gis2_rubrics:
            return []
        country = (self.countries[0] if self.countries else "").strip()
        domain = self.gis2_domain or GIS2_DOMAINS.get(country.lower(), "ru")
        return [
            Gis2Target(
                country=country,
                city_code=city,
                domain=domain,
                rubrics=[dict(r) for r in self.gis2_rubrics],
            )
            for city in self.gis2_cities
        ]


@dataclass
class CampaignConfig:
    """Содержимое ``lead_campaigns.yaml`` целиком."""

    campaigns: dict[str, Campaign] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)
    path: str = ""

    def get(self, name: str) -> Campaign:
        """Кампания по имени. Кидает CampaignError со списком доступных."""
        campaign = self.campaigns.get(name)
        if campaign is None:
            available = ", ".join(sorted(self.campaigns)) or "(нет ни одной)"
            raise CampaignError(f"Кампания '{name}' не найдена. Доступные: {available}")
        return campaign

    @property
    def names(self) -> list[str]:
        return sorted(self.campaigns)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _validate_rubrics(raw: list[dict[str, Any]], campaign_name: str) -> list[dict[str, str]]:
    """Проверить рубрики 2ГИС: у каждой обязателен и code, и name."""
    rubrics: list[dict[str, str]] = []
    for item in raw:
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        if not code or not name:
            raise CampaignError(
                f"Кампания '{campaign_name}': рубрика 2ГИС требует и code, и name "
                f"(получено: code={code!r}, name={name!r})"
            )
        rubrics.append({"code": code, "name": name})
    return rubrics


def _campaign_from_dict(name: str, body: dict[str, Any]) -> Campaign:
    """Собрать Campaign из словаря YAML с валидацией полей кампании."""
    gis2_raw = body.get("gis2") or {}
    if not isinstance(gis2_raw, dict):
        raise CampaignError(f"Кампания '{name}': секция gis2 должна быть словарём")

    language = str(body.get("language") or "ru").strip().lower()
    if language not in VALID_LANGUAGES:
        raise CampaignError(
            f"Кампания '{name}': language должен быть одним из "
            f"{sorted(VALID_LANGUAGES)} (получено: {language!r})"
        )

    direction = str(body.get("direction") or "import").strip().lower()
    if direction not in VALID_DIRECTIONS:
        raise CampaignError(
            f"Кампания '{name}': direction должен быть import или export "
            f"(получено: {direction!r})"
        )

    cities = [c.strip().lower() for c in _as_str_list(gis2_raw.get("cities"))]
    rubrics = _validate_rubrics(
        [r for r in (gis2_raw.get("rubrics") or []) if isinstance(r, dict)],
        name,
    )

    return Campaign(
        name=str(name),
        niche_name=str(body.get("niche_name") or "").strip(),
        keywords_en=_as_str_list(body.get("keywords_en")),
        keywords_ru=_as_str_list(body.get("keywords_ru")),
        hs_codes=_as_str_list(body.get("hs_codes")),
        target_industries=_as_str_list(body.get("target_industries")),
        direction=direction,
        language=language,
        countries=_as_str_list(body.get("countries")),
        gis2_domain=str(gis2_raw.get("domain") or "").strip().lower(),
        gis2_cities=cities,
        gis2_rubrics=rubrics,
    )


def load_campaigns(path: str | Path | None = None) -> CampaignConfig:
    """Прочитать и разобрать YAML с кампаниями.

    Args:
        path: Путь к файлу. По умолчанию — ``config/lead_campaigns.yaml``
            (или ``LEADS_CAMPAIGNS_PATH``).

    Returns:
        :class:`CampaignConfig` со всеми кампаниями и лимитами.

    Raises:
        CampaignError: файла нет, YAML битый, кампаний нет или поля невалидны.
    """
    from shared.config import leads_campaigns_path

    target = Path(path) if path else Path(leads_campaigns_path())

    if not target.exists():
        raise CampaignError(
            f"Файл кампаний не найден: {target}. "
            "Скопируйте config/lead_campaigns.yaml или задайте LEADS_CAMPAIGNS_PATH."
        )

    try:
        import yaml
    except ImportError as e:  # pragma: no cover - зависит от окружения
        raise CampaignError(
            "Не установлен PyYAML. Установите: pip install -r requirements-parser.txt"
        ) from e

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise CampaignError(f"Не удалось разобрать {target}: {e}") from e

    if not isinstance(raw, dict):
        raise CampaignError(f"{target}: ожидался словарь на верхнем уровне")

    campaigns: dict[str, Campaign] = {}
    for name, body in (raw.get("campaigns") or {}).items():
        if not isinstance(body, dict):
            logger.warning(f"{target}: кампания '{name}' пропущена — ожидался словарь")
            continue
        campaigns[str(name)] = _campaign_from_dict(str(name), body)

    if not campaigns:
        raise CampaignError(f"{target}: не определено ни одной кампании")

    config = CampaignConfig(
        campaigns=campaigns,
        limits=Limits.from_dict(raw.get("limits")),
        path=str(target),
    )
    logger.debug(f"Загружено кампаний: {len(campaigns)} из {target}")
    return config


__all__ = [
    "Campaign",
    "CampaignConfig",
    "CampaignError",
    "Gis2Section",
    "GIS2_DOMAINS",
    "VALID_DIRECTIONS",
    "VALID_LANGUAGES",
    "load_campaigns",
]
