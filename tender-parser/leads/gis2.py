"""Сбор компаний из 2ГИС (РФ + Казахстан) поверх parser-2gis.

В отличие от каталогов импортёров (allbiz / made-in-china / tradekey), 2ГИС —
гео-каталог организаций: компании ищутся по рубрике и городу, а не по ключевому
слову товара. Обход идёт через браузер (Chrome), поэтому запускается на машине
с установленным Chrome и CLI ``parser-2gis`` (VM / GitHub Actions), а не на
Vercel.

parser-2gis требует pydantic v1, тогда как этот проект — v2, поэтому парсер
вызывается как внешний процесс (его собственный venv), а не импортируется.
Слой модуля разделён на чистые функции (построение URL и маппинг карточки 2ГИС
в ``LeadCompany``) и оркестрацию :func:`collect_gis2`, которая ходит в CLI
через ``subprocess`` — модуль импортируется и тестируется без Chrome.

См. config/gis2_targets.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
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


def _extract_real_website(raw: str) -> str:
    """Достать настоящий сайт из redirect-обёртки 2ГИС.

    2ГИС отдаёт сайт компании как ``http://link.2gis.ru/<hash>?<реальный_url>``:
    настоящий адрес лежит в query-строке. Если ``?`` есть и после него идёт
    URL — возвращаем часть после ``?``; иначе строку как есть.
    """
    if "?" in raw:
        _, _, query = raw.partition("?")
        if query.startswith(("http://", "https://")):
            return query
    return raw


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
    website_raw = _extract_real_website(_first_contact(item, "website"))
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


def _scrape_url(
    url: str,
    *,
    parser_bin: str = "parser-2gis",
    max_records: int = 0,
) -> list[dict[str, Any]]:
    """Обойти один URL выдачи 2ГИС через CLI parser-2gis и вернуть карточки.

    parser-2gis пишет результат в JSON-файл (массив сырых карточек каталога).
    Вызов идёт через ``subprocess``, потому что parser-2gis тянет pydantic v1 и
    живёт в отдельном venv.

    Args:
        url: URL выдачи 2ГИС.
        parser_bin: Путь к исполняемому файлу parser-2gis (по умолчанию в PATH).
        max_records: Максимум записей с URL; ``0`` — лимит parser-2gis.

    Returns:
        Список сырых карточек (пустой при ошибке/отсутствии результата).
    """
    import json
    import os
    import subprocess
    import tempfile

    fd, path = tempfile.mkstemp(prefix="gis2_", suffix=".json")
    os.close(fd)
    try:
        cmd = [parser_bin, "-i", url, "-o", path, "-f", "json", "--chrome.headless", "yes"]
        if max_records > 0:
            cmd += ["--parser.max-records", str(max_records)]
        subprocess.run(cmd, check=False, capture_output=True, timeout=3600)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    finally:
        if os.path.exists(path):
            os.unlink(path)


def collect_gis2(
    targets: list[Gis2Target],
    repository: Any,
    *,
    profile: str = "",
    parser_bin: str = "parser-2gis",
    max_records: int = 0,
) -> tuple[int, int]:
    """Обойти цели 2ГИС и записать компании в хранилище лидов.

    Скрейпинг идёт через CLI parser-2gis (Chrome в отдельном venv), затем
    карточки маппятся в :class:`LeadCompany` и пишутся в хранилище.

    Args:
        targets: Список целей (:class:`Gis2Target`).
        repository: Хранилище лидов (``get_leads_repository``).
        profile: Имя ниши, под которое записываются компании.
        parser_bin: Путь к CLI parser-2gis (по умолчанию ``parser-2gis`` в PATH).
        max_records: Максимум записей с одного URL; ``0`` — лимит parser-2gis.

    Returns:
        Кортеж ``(вставлено, обновлено)``.
    """
    inserted = updated = 0
    for target in targets:
        for rubric in target.rubrics:
            url = build_search_url(target.domain, target.city_code, rubric["name"], rubric["code"])
            items = _scrape_url(url, parser_bin=parser_bin, max_records=max_records)
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
