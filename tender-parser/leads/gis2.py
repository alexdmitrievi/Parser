"""Сбор компаний из 2ГИС (РФ + Казахстан) поверх parser-2gis.

В отличие от каталогов импортёров (allbiz / made-in-china / tradekey), 2ГИС —
гео-каталог организаций: компании ищутся по рубрике и городу, а не по ключевому
слову товара. Обход идёт через браузер (Chrome), поэтому запускается на машине
с установленным Chrome и пакетом ``parser-2gis`` (VM / GitHub Actions), а не на
Vercel и не в окружении тендерного парсера.

Модуль разделён на чистые функции (построение URL и маппинг карточки 2ГИС в
``LeadCompany``) и оркестрацию :func:`collect_gis2`, которая тянет parser-2gis
лениво — поэтому модуль импортируется и тестируется без браузера.

См. config/gis2_targets.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self
from urllib.parse import quote_plus

from leads.emails import classify, is_junk, normalize_email
from leads.models import LeadCompany, LeadEmail, utcnow
from leads.normalizer import is_company_domain, normalize_domain, normalize_website

SOURCE_ID = "2gis"

# Ключи значения контакта в порядке убывания доверия.
_CONTACT_VALUE_KEYS = ("value", "url", "text")


@dataclass
class Gis2Target:
    """Цель обхода: страна + город + рубрики.

    ``rubrics`` — список словарей ``{"code": ..., "name": ...}``, где ``code`` —
    идентификатор рубрики 2ГИС (data/rubrics.json), а ``name`` — человекочитаемое
    название (оно же поисковый запрос в URL).
    """

    country: str                              # "Russia" | "Kazakhstan"
    city_code: str                            # код города 2ГИС (например "omsk")
    domain: str                               # домен 2ГИС (например "ru")
    rubrics: list[dict[str, str]] = field(default_factory=list)


def build_search_url(domain: str, city_code: str, query: str, rubric_id: str = "") -> str:
    """Построить URL выдачи 2ГИС по городу и рубрике/запросу.

    Args:
        domain: Домен 2ГИС (``ru``, ``kz`` и т.д.).
        city_code: Код города (``omsk``, ``almaty`` …).
        query: Поисковый запрос (обычно название рубрики).
        rubric_id: Необязательный код рубрики; добавляется как ``/rubricId/<code>``.

    Returns:
        URL вида ``https://2gis.ru/omsk/search/…/rubricId/614/filters/sort=name``.
    """
    base = f"https://2gis.{domain}/{city_code}"
    rest = f"/search/{quote_plus(query)}"
    if rubric_id:
        rest += f"/rubricId/{rubric_id}"
    return base + rest + "/filters/sort=name"


def _company_name(item: dict[str, Any]) -> str:
    """Имя организации: ``name`` → ``name_ex.primary`` → ``org.name``."""
    for source in (
        item.get("name"),
        (item.get("name_ex") or {}).get("primary"),
        (item.get("org") or {}).get("name"),
    ):
        if source:
            return str(source).strip()
    return ""


def _contacts_of_type(item: dict[str, Any], type_: str) -> list[str]:
    """Все значения контактов заданного типа из всех групп контактов."""
    found: list[str] = []
    for group in item.get("contact_groups") or []:
        for contact in group.get("contacts") or []:
            if contact.get("type") != type_:
                continue
            for key in _CONTACT_VALUE_KEYS:
                value = contact.get(key)
                if value and str(value).strip():
                    found.append(str(value).strip())
                    break
    return found


def _first_contact(item: dict[str, Any], type_: str) -> str:
    """Первое непустое значение контакта заданного типа."""
    values = _contacts_of_type(item, type_)
    return values[0] if values else ""


def _region(item: dict[str, Any]) -> str:
    """Название региона из административного деления (best-effort)."""
    for div in item.get("adm_div") or []:
        kind = (div.get("type") or "").lower()
        if any(mark in kind for mark in ("region", "province", "obl", "okrug")):
            name = (div.get("name") or "").strip()
            if name:
                return name
    return ""


def _activity(item: dict[str, Any]) -> str:
    """Вид деятельности: названия рубрик через запятую."""
    names = [str(r.get("name", "")).strip() for r in (item.get("rubrics") or [])]
    return ", ".join(n for n in names if n)


def catalog_item_to_company(
    item: dict[str, Any],
    *,
    country: str,
    profile: str = "",
    source_name: str = SOURCE_ID,
) -> LeadCompany | None:
    """Преобразовать карточку каталога 2ГИС в :class:`LeadCompany`.

    Args:
        item: Сырой элемент из ответа ``items/byid`` (структура
            ``result.items[0]``, как её отдаёт JSONWriter parser-2gis).
        country: Страна на английском (``Russia`` / ``Kazakhstan``).
        profile: Имя ниши/профиля, под которое попала компания.
        source_name: Метка источника в ``source_name``.

    Returns:
        Карточка компании либо ``None``, если из элемента не извлечь ни имени,
        ни сайта (неидентифицируемая запись отбрасывается).
    """
    name = _company_name(item)
    website_raw = _first_contact(item, "website")
    website = normalize_website(website_raw) if website_raw else ""
    domain = normalize_domain(website_raw) if website_raw else ""
    if domain and not is_company_domain(domain):
        domain = ""

    if not name and not domain:
        return None

    emails: list[LeadEmail] = []
    for raw in _contacts_of_type(item, "email"):
        email = normalize_email(raw)
        if not email or is_junk(email):
            continue
        emails.append(LeadEmail(email=email, kind=classify(email)))

    phones = _contacts_of_type(item, "phone")
    whatsapp = _first_contact(item, "whatsapp")
    telegram = _first_contact(item, "telegram")

    firm_id = str(item.get("id", "")).split("_", 1)[0]
    source_url = f"https://2gis.com/firm/{firm_id}" if firm_id else ""

    now = utcnow()
    return LeadCompany(
        company_name_en=name,
        city=str(item.get("city_alias") or "").strip(),
        province=_region(item),
        country=country,
        website=website,
        domain=domain,
        emails=emails,
        phones=phones,
        whatsapp=whatsapp,
        wechat=telegram,  # поле названо wechat в схеме, но храним telegram-контакт
        matched_keywords=[name] if name else [],
        profile=profile,
        activity=_activity(item),
        source_url=source_url,
        source_name=source_name,
        first_seen=now,
        last_seen=now,
        enrich_status="pending" if domain else "no_site",
    )


def load_targets(path: str | Path | None = None) -> tuple[str, list[Gis2Target]]:
    """Прочитать цели обхода из YAML (по умолчанию config/gis2_targets.yaml).

    Args:
        path: Путь к файлу. По умолчанию — ``config/gis2_targets.yaml``.

    Returns:
        Кортеж ``(profile, targets)``, где ``profile`` — имя ниши для всей
        выгрузки, а ``targets`` — список :class:`Gis2Target`.

    Raises:
        RuntimeError: файл отсутствует, битый или без целей.
    """
    target = Path(path) if path else Path("config/gis2_targets.yaml")
    if not target.exists():
        raise RuntimeError(f"Файл целей 2ГИС не найден: {target}")

    try:
        import yaml
    except ImportError as e:  # pragma: no cover - зависит от окружения
        raise RuntimeError("Не установлен PyYAML: pip install -r requirements-parser.txt") from e

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise RuntimeError(f"Не удалось разобрать {target}: {e}") from e

    profile = str(raw.get("profile") or "").strip()
    targets: list[Gis2Target] = []
    for body in raw.get("targets") or []:
        if not isinstance(body, dict):
            continue
        rubrics = [dict(r) for r in (body.get("rubrics") or []) if isinstance(r, dict)]
        if not rubrics:
            continue
        targets.append(
            Gis2Target(
                country=str(body.get("country") or "").strip(),
                city_code=str(body.get("city_code") or "").strip(),
                domain=str(body.get("domain") or "ru").strip(),
                rubrics=rubrics,
            )
        )

    if not targets:
        raise RuntimeError(f"{target}: не определено ни одной цели обхода")
    return profile, targets


class _ListWriter:
    """Минимальный writer, собирающий карточки в список вместо файла.

    Повторяет интерфейс ``parser_2gis.writer.FileWriter`` (метод ``write`` +
    контекстный менеджер), который использует ``MainParser.parse``.
    """

    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def write(self, catalog_doc: Any) -> None:
        try:
            items = catalog_doc["result"]["items"]
        except (KeyError, TypeError):
            return
        if isinstance(items, list):
            self._sink.extend(i for i in items if isinstance(i, dict))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _scrape_url(
    url: str,
    chrome_options: Any,
    parser_options: Any,
) -> list[dict[str, Any]]:
    """Обойти один URL выдачи 2ГИС и вернуть сырые карточки."""
    from parser_2gis.parser import get_parser

    items: list[dict[str, Any]] = []
    with _ListWriter(items) as writer, get_parser(url, chrome_options, parser_options) as parser:
        parser.parse(writer)
    return items


def collect_gis2(
    targets: list[Gis2Target],
    repository: Any,
    *,
    profile: str = "",
    max_records: int = 0,
    headless: bool = True,
) -> tuple[int, int]:
    """Обойти цели 2ГИС и записать компании в хранилище лидов.

    Args:
        targets: Список целей (:class:`Gis2Target`).
        repository: Хранилище лидов (``get_leads_repository``).
        profile: Имя ниши, под которое записываются компании.
        max_records: Максимум записей с одного URL; ``0`` — лимит parser-2gis.
        headless: Запускать Chrome без окна (обязательно на сервере).

    Returns:
        Кортеж ``(вставлено, обновлено)``.

    Raises:
        RuntimeError: parser-2gis не установлен (нужен Chrome-хост).
    """
    try:
        from parser_2gis.chrome.options import ChromeOptions
        from parser_2gis.parser.options import ParserOptions
    except ImportError as e:
        raise RuntimeError(
            "parser-2gis не установлен. Сбор 2ГИС запускается только на хосте "
            "с Chrome: pip install parser-2gis"
        ) from e

    chrome_options = ChromeOptions(headless=headless, disable_images=True, silent_browser=True)
    parser_options = ParserOptions(max_records=max_records) if max_records > 0 else ParserOptions()

    inserted = updated = 0
    for target in targets:
        for rubric in target.rubrics:
            url = build_search_url(target.domain, target.city_code, rubric["name"], rubric["code"])
            items = _scrape_url(url, chrome_options, parser_options)
            companies = [
                c
                for item in items
                if (c := catalog_item_to_company(item, country=target.country, profile=profile))
                is not None
            ]
            if not companies:
                continue
            ins, upd = repository.upsert_companies(companies)
            inserted += ins
            updated += upd
    return inserted, updated


__all__ = [
    "SOURCE_ID",
    "Gis2Target",
    "build_search_url",
    "catalog_item_to_company",
    "collect_gis2",
    "load_targets",
]
