"""Разведка структуры FTP ЕИС — запустить на VPS перед первым циклом.

Проверяет реквизиты доступа, находит каталоги Омской и Новосибирской
областей для 44-ФЗ и 223-ФЗ и показывает, какие подкаталоги с архивами
реально существуют (имена каталогов на FTP транслитерируются
неконсистентно, поэтому код ищет их по подстроке).

Использование:
    python scripts/eis_ftp_probe.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.env import load_dotenv  # noqa: E402

load_dotenv()

from engine.fetchers.ftp_fetcher import FtpFetcher  # noqa: E402
from engine.sources.tenders.eis_ftp import (  # noqa: E402
    DEFAULT_REGIONS, LAYOUT_44, LAYOUT_223,
    PROTOCOL_LAYOUT_44, PROTOCOL_LAYOUT_223, _region_match,
)


def main() -> int:
    host = os.environ.get("EIS_FTP_HOST", "ftp.zakupki.gov.ru")
    user = os.environ.get("EIS_FTP_USER", "free")
    passwd = os.environ.get("EIS_FTP_PASS", "free")

    print(f"Connecting to {host} as {user!r}...")
    with FtpFetcher() as ftp:
        try:
            ftp.connect(host, user=user, passwd=passwd)
        except Exception as e:
            print(f"FAIL: cannot connect/login: {e}")
            print("Попробуйте EIS_FTP_USER=anonymous EIS_FTP_PASS= в .env")
            return 1
        print("Connected OK\n")

        for layout in (LAYOUT_44, LAYOUT_223, PROTOCOL_LAYOUT_44, PROTOCOL_LAYOUT_223):
            print(f"── {layout.law_type} @ {layout.base_dir} ──")
            entries = ftp.list_dirs(layout.base_dir)
            if not entries:
                print(f"  FAIL: {layout.base_dir} пуст или недоступен\n")
                continue
            print(f"  {len(entries)} entries in {layout.base_dir}")

            for region in DEFAULT_REGIONS:
                region_dir = _region_match(entries, region)
                if not region_dir:
                    sample = ", ".join(sorted(entries)[:10])
                    print(f"  FAIL: '{region.display_name}' не найдена. Примеры: {sample}")
                    continue
                print(f"  {region.display_name} → {region_dir}")
                for subdir in layout.subdir_candidates:
                    path = f"{layout.base_dir}/{region_dir}/{subdir}"
                    files = ftp.list_files(path, pattern="*.xml.zip")
                    marker = "OK " if files else "-- "
                    print(f"    {marker}{path}: {len(files)} архивов"
                          + (f", например {files[-1].rsplit('/', 1)[-1]}" if files else ""))
                # Показать, что вообще есть в каталоге региона
                region_entries = ftp.list_dirs(f"{layout.base_dir}/{region_dir}")
                names = [e.rsplit("/", 1)[-1] for e in region_entries[:20]]
                print(f"    содержимое каталога региона: {names}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
