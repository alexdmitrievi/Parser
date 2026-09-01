"""Разбор файлов-сидов: домены (.txt) и CSV/Excel со списком компаний.

Позволяет грузить списки компаний из любого источника (выгрузки Volza,
госреестры, каталоги TİM, собственные контакты) и отдавать их в пайплайн
как карточки с сайтом, названием, страной и кодом ТН ВЭД.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SeedRecord:
    """Одна строка файла-сида: компания с сайтом и необязательными метками."""

    website: str = ""
    name: str = ""
    country: str = ""
    hs_code: str = ""


def parse_seed_file(path: str | Path) -> list[SeedRecord]:
    """Разобрать файл-сид по расширению.

    Args:
        path: Путь к файлу.

    Returns:
        Список карточек SeedRecord.

    Raises:
        FileNotFoundError: файла нет.
        ValueError: неподдерживаемое расширение.
        RuntimeError: для .xlsx не установлен openpyxl.

    Форматы:
        * ``.txt`` — по одному домену в строке, ``#`` — комментарий.
        * ``.csv`` — столбцы ``name``, ``website``/``domain``,
          ``country``, ``hs_code`` (обязателен только сайт/домен).
        * ``.xlsx`` — те же столбцы, первый лист.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Файл сида не найден: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _parse_txt(path)
    if suffix == ".csv":
        return _parse_csv(path)
    if suffix in (".xlsx", ".xls"):
        return _parse_xlsx(path)
    raise ValueError(f"Неподдерживаемый формат сида: {suffix} (нужны .txt/.csv/.xlsx)")


def _parse_txt(path: Path) -> list[SeedRecord]:
    records: list[SeedRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            records.append(SeedRecord(website=token))
    return records


def _parse_csv(path: Path) -> list[SeedRecord]:
    records: list[SeedRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        for row in reader:
            record = _from_row(row)
            if record.website:
                records.append(record)
    return records


def _parse_xlsx(path: Path) -> list[SeedRecord]:
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:  # pragma: no cover - среда без openpyxl
        raise RuntimeError("Для .xlsx установите openpyxl") from exc

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    try:
        headers = [str(c).strip() if c is not None else "" for c in next(rows)]
    except StopIteration:
        return []
    records: list[SeedRecord] = []
    for values in rows:
        row = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
        record = _from_row(row)
        if record.website:
            records.append(record)
    return records


def _from_row(row: dict[str, Any]) -> SeedRecord:
    def pick(*keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    return SeedRecord(
        website=pick("website", "domain", "site", "url"),
        name=pick("name", "company", "company_name"),
        country=pick("country", "country_code"),
        hs_code=pick("hs_code", "hs", "hscode"),
    )


__all__ = ["SeedRecord", "parse_seed_file"]
