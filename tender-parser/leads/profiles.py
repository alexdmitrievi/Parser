"""Загрузка профилей продуктов из config/leads_profiles.yaml.

Файл читается заново при каждом обращении к :func:`load_profiles` — правки в
YAML применяются на следующем запуске без изменения кода.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared.config import leads_profiles_path
from engine.observability.logger import get_logger

logger = get_logger("leads.profiles")

DEFAULT_MAX_PAGES = 20
DEFAULT_DELAY_SECONDS = 3.0
DEFAULT_MAX_CONCURRENCY = 2

# Вежливый режим — нижние границы, которые конфиг не может ослабить.
MIN_DELAY_SECONDS = 1.0
MAX_ALLOWED_CONCURRENCY = 2


class ProfileError(Exception):
    """Профиль не найден или конфиг невалиден."""


@dataclass
class Limits:
    """Ограничения обхода. Значения жёстко зажаты вежливым режимом."""

    max_pages_per_query: int = DEFAULT_MAX_PAGES
    request_delay_seconds: float = DEFAULT_DELAY_SECONDS
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> Limits:
        raw = raw or {}
        delay = _as_float(raw.get("request_delay_seconds"), DEFAULT_DELAY_SECONDS)
        concurrency = _as_int(raw.get("max_concurrency"), DEFAULT_MAX_CONCURRENCY)

        if delay < MIN_DELAY_SECONDS:
            logger.warning(
                f"request_delay_seconds={delay} ниже минимума {MIN_DELAY_SECONDS}s — поднимаю"
            )
            delay = MIN_DELAY_SECONDS
        if concurrency > MAX_ALLOWED_CONCURRENCY:
            logger.warning(
                f"max_concurrency={concurrency} выше потолка {MAX_ALLOWED_CONCURRENCY} — снижаю"
            )
            concurrency = MAX_ALLOWED_CONCURRENCY

        return cls(
            max_pages_per_query=max(1, _as_int(raw.get("max_pages_per_query"), DEFAULT_MAX_PAGES)),
            request_delay_seconds=delay,
            max_concurrency=max(1, concurrency),
        )


@dataclass
class Profile:
    """Профиль продукта: чем искать и во что целиться."""

    name: str
    keywords_en: list[str] = field(default_factory=list)
    keywords_zh: list[str] = field(default_factory=list)
    hs_codes: list[str] = field(default_factory=list)
    target_industries: list[str] = field(default_factory=list)

    @property
    def all_keywords(self) -> list[str]:
        """Все ключевые слова профиля, английские первыми."""
        return [*self.keywords_en, *self.keywords_zh]

    def match(self, text: str) -> list[str]:
        """Какие ключевые слова профиля встречаются в тексте.

        Регистронезависимо для латиницы; для иероглифов регистра нет.
        """
        if not text:
            return []
        lowered = text.lower()
        return [kw for kw in self.all_keywords if kw.lower() in lowered]

    def guess_industry(self, text: str) -> str:
        """Первая отрасль из target_industries, упомянутая в тексте."""
        if not text:
            return ""
        lowered = text.lower()
        for industry in self.target_industries:
            if industry.lower() in lowered:
                return industry
        return ""


@dataclass
class ProfileConfig:
    """Содержимое leads_profiles.yaml целиком."""

    profiles: dict[str, Profile] = field(default_factory=dict)
    regions_priority: list[str] = field(default_factory=list)
    limits: Limits = field(default_factory=Limits)
    path: str = ""

    def get(self, name: str) -> Profile:
        """Профиль по имени. Кидает ProfileError со списком доступных."""
        profile = self.profiles.get(name)
        if profile is None:
            available = ", ".join(sorted(self.profiles)) or "(нет ни одного)"
            raise ProfileError(f"Профиль '{name}' не найден. Доступные: {available}")
        return profile

    def region_rank(self, province: str) -> int:
        """Позиция провинции в regions_priority; хвост — для остальных."""
        if not province:
            return len(self.regions_priority) + 1
        lowered = province.strip().lower()
        for index, region in enumerate(self.regions_priority):
            if region.lower() == lowered:
                return index
        return len(self.regions_priority)

    @property
    def names(self) -> list[str]:
        return sorted(self.profiles)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def load_profiles(path: str | Path | None = None) -> ProfileConfig:
    """Прочитать и разобрать YAML с профилями.

    Args:
        path: Путь к файлу. По умолчанию — LEADS_PROFILES_PATH или
            config/leads_profiles.yaml.

    Raises:
        ProfileError: файла нет, YAML битый или не установлен PyYAML.
    """
    target = Path(path) if path else Path(leads_profiles_path())

    if not target.exists():
        raise ProfileError(
            f"Файл профилей не найден: {target}. "
            "Скопируйте config/leads_profiles.yaml или задайте LEADS_PROFILES_PATH."
        )

    try:
        import yaml
    except ImportError as e:  # pragma: no cover - зависит от окружения
        raise ProfileError(
            "Не установлен PyYAML. Установите: pip install -r requirements-parser.txt"
        ) from e

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise ProfileError(f"Не удалось разобрать {target}: {e}") from e

    if not isinstance(raw, dict):
        raise ProfileError(f"{target}: ожидался словарь на верхнем уровне")

    profiles: dict[str, Profile] = {}
    for name, body in (raw.get("profiles") or {}).items():
        if not isinstance(body, dict):
            logger.warning(f"{target}: профиль '{name}' пропущен — ожидался словарь")
            continue
        profiles[str(name)] = Profile(
            name=str(name),
            keywords_en=_as_str_list(body.get("keywords_en")),
            keywords_zh=_as_str_list(body.get("keywords_zh")),
            hs_codes=_as_str_list(body.get("hs_codes")),
            target_industries=_as_str_list(body.get("target_industries")),
        )

    if not profiles:
        raise ProfileError(f"{target}: не определён ни один профиль")

    config = ProfileConfig(
        profiles=profiles,
        regions_priority=_as_str_list(raw.get("regions_priority")),
        limits=Limits.from_dict(raw.get("limits")),
        path=str(target),
    )
    logger.debug(f"Загружено профилей: {len(profiles)} из {target}")
    return config


__all__ = ["Profile", "ProfileConfig", "Limits", "ProfileError", "load_profiles"]
