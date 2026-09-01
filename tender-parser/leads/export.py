"""Экспорт лидов в CSV для Coldy.

Формат: одна строка — один адрес. Колонки фиксированы:
``Company``, ``Email``, ``Website``, ``Province``, ``City``, ``Profile``, ``Source``.

Два правила, которые применяются всегда:

* **Список исключений.** Домены и адреса из ``config/leads_blacklist.txt``
  не выгружаются никогда. Туда же добавляются отписавшиеся.
* **PIPL.** По умолчанию выгружаются только ролевые адреса (``info@``,
  ``sales@``, ``export@`` и подобные). Персональные собираются и хранятся, но
  попадают в файл лишь при явном ``--include-personal``. О правовых рисках —
  раздел «Правовые ограничения» в docs/LEADS.md.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from engine.observability.logger import get_logger
from leads.blacklist import Blacklist
from leads.models import LeadCompany
from leads.profiles import ProfileConfig

logger = get_logger("leads.export")

# Первые семь колонок — формат Coldy, порядок менять нельзя. Дальше добавлены
# вид деятельности и предложения/запросы (см. docs/LEADS.md).
CSV_COLUMNS = (
    "Company", "Email", "Website", "Province", "City", "Country", "Profile", "Source",
    "Activity", "Offers", "Requests",
)

# utf-8-sig — чтобы Excel не ломал китайские названия при открытии файла.
DEFAULT_ENCODING = "utf-8-sig"


@dataclass
class ExportResult:
    """Итог выгрузки."""

    path: str
    rows: int = 0
    companies: int = 0
    skipped_blacklist: int = 0
    skipped_personal: int = 0
    skipped_no_email: int = 0

    def summary(self) -> str:
        return (
            f"{self.rows} строк из {self.companies} компаний → {self.path}\n"
            f"  пропущено: по списку исключений {self.skipped_blacklist}, "
            f"персональных {self.skipped_personal}, "
            f"без почты {self.skipped_no_email}"
        )


def build_rows(
    companies: Iterable[LeadCompany],
    blacklist: Blacklist | None = None,
    include_personal: bool = False,
    profiles: ProfileConfig | None = None,
) -> tuple[list[dict[str, str]], ExportResult]:
    """Собрать строки CSV из компаний.

    Args:
        companies: Компании для выгрузки.
        blacklist: Список исключений. ``None`` — не фильтровать.
        include_personal: Включить персональные адреса (см. предупреждение о PIPL).
        profiles: Конфиг профилей — для сортировки по приоритету провинций.

    Returns:
        ``(строки, статистика)``. Строки отсортированы по приоритету провинции,
        затем по названию компании.
    """
    result = ExportResult(path="")
    rows: list[dict[str, str]] = []
    ranked: list[tuple[int, str, dict[str, str]]] = []

    for company in companies:
        result.companies += 1

        if blacklist and company.domain and blacklist.blocks_domain(company.domain):
            result.skipped_blacklist += len(company.emails)
            continue

        emails = company.emails if include_personal else company.role_emails
        if not include_personal:
            result.skipped_personal += len(company.personal_emails)

        if not emails:
            result.skipped_no_email += 1
            continue

        rank = profiles.region_rank(company.province) if profiles else 0
        name = company.display_name

        for item in emails:
            if blacklist and blacklist.blocks_email(item.email):
                result.skipped_blacklist += 1
                continue
            ranked.append((
                rank,
                name.lower(),
                {
                    "Company": name,
                    "Email": item.email,
                    "Website": company.website,
                    "Province": company.province,
                    "City": company.city,
                    "Country": company.country,
                    "Profile": company.profile,
                    "Source": company.source_name,
                    "Activity": company.activity,
                    "Offers": " | ".join(company.offers),
                    "Requests": " | ".join(company.requests),
                },
            ))

    ranked.sort(key=lambda triple: (triple[0], triple[1]))
    rows = [row for _rank, _name, row in ranked]
    result.rows = len(rows)
    return rows, result


def export_csv(
    companies: Iterable[LeadCompany],
    out_path: str | Path,
    blacklist: Blacklist | None = None,
    include_personal: bool = False,
    profiles: ProfileConfig | None = None,
    encoding: str = DEFAULT_ENCODING,
) -> ExportResult:
    """Выгрузить лиды в CSV-файл под Coldy.

    Файл пишется даже когда строк нет — с одним заголовком, чтобы загрузка в
    Coldy не падала на пустом входе.
    """
    rows, result = build_rows(
        companies,
        blacklist=blacklist,
        include_personal=include_personal,
        profiles=profiles,
    )

    target = Path(out_path)
    if target.parent and str(target.parent) not in ("", "."):
        target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    result.path = str(target)
    logger.info(result.summary())
    return result


__all__ = ["export_csv", "build_rows", "ExportResult", "CSV_COLUMNS", "DEFAULT_ENCODING"]
