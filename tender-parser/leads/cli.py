"""CLI домена leads.

    python -m leads collect --profile petcoke_anode
    python -m leads collect --profile grain --from-file domains.txt
    python -m leads enrich
    python -m leads export --profile petcoke_anode --out leads.csv
    python -m leads stats

Все команды — no-op при ``LEADS_ENABLED=false`` (значение по умолчанию):
печатается подсказка и возвращается код 0, чтобы выключенный домен не ронял
расписание.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from engine.observability.logger import setup_logging
from leads.blacklist import Blacklist
from leads.export import DEFAULT_ENCODING, export_csv
from leads.seed import parse_seed_file
from leads.pipeline import LeadsPipeline
from leads.profiles import ProfileError, load_profiles
from leads.storage import get_leads_repository

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

DISABLED_MESSAGE = (
    "LEADS_ENABLED=false — домен leads выключен, ничего не делаю.\n"
    "Чтобы включить: LEADS_ENABLED=true в .env (см. docs/LEADS.md)."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m leads",
        description="Сбор китайских компаний-импортёров и их контактных почт.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python -m leads collect --profile petcoke_anode\n"
            "  python -m leads collect --profile grain --from-file domains.txt\n"
            "  python -m leads enrich --limit 50\n"
            "  python -m leads export --profile petcoke_anode --out leads.csv\n"
            "  python -m leads stats\n"
        ),
    )
    parser.add_argument("--log-level", default="INFO", help="Уровень логирования (по умолчанию INFO)")
    parser.add_argument(
        "--profiles-config",
        default="",
        help="Путь к YAML с профилями (по умолчанию config/leads_profiles.yaml)",
    )
    parser.add_argument(
        "--storage",
        default="",
        choices=["", "sqlite", "supabase"],
        help="Бэкенд хранения; по умолчанию берётся из LEADS_STORAGE",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="Собрать компании из каталогов")
    collect.add_argument("--profile", required=True, help="Имя профиля из leads_profiles.yaml")
    collect.add_argument(
        "--source",
        action="append",
        default=None,
        metavar="ID",
        help="Запустить только указанный адаптер (можно повторять)",
    )
    collect.add_argument(
        "--from-file",
        metavar="PATH",
        help=(
            "Файл со списком доменов (по одному в строке). Добавляет компании "
            "напрямую, без обхода каталога — если каталог закрыт robots.txt"
        ),
    )

    enrich = sub.add_parser("enrich", help="Обойти сайты компаний и добрать почты")
    enrich.add_argument("--profile", default="", help="Ограничить профилем")
    enrich.add_argument("--limit", type=int, default=0, help="Максимум компаний за прогон")
    enrich.add_argument(
        "--retry-failed",
        action="store_true",
        help="Повторить домены, ранее давшие blocked / skipped_robots",
    )

    export = sub.add_parser("export", help="Выгрузить CSV под Coldy")
    export.add_argument("--profile", default="", help="Ограничить профилем")
    export.add_argument("--out", required=True, help="Путь к CSV-файлу")
    export.add_argument(
        "--include-personal",
        action="store_true",
        help=(
            "Включить персональные адреса. ВНИМАНИЕ: повышает правовые риски "
            "по PIPL — см. docs/LEADS.md"
        ),
    )
    export.add_argument("--encoding", default="", help="Кодировка CSV (по умолчанию utf-8-sig)")

    stats = sub.add_parser("stats", help="Сводка по собранным лидам")
    stats.add_argument("--profile", default="", help="Ограничить профилем")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа CLI. Возвращает код завершения процесса."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.log_level)
    logging.getLogger("leads").setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

    from shared.config import leads_enabled

    if not leads_enabled():
        print(DISABLED_MESSAGE)
        return EXIT_OK

    try:
        profiles = load_profiles(args.profiles_config or None)
    except ProfileError as e:
        print(f"Ошибка конфигурации профилей: {e}", file=sys.stderr)
        return EXIT_USAGE

    try:
        repository = get_leads_repository(args.storage or None)
    except (ValueError, RuntimeError) as e:
        print(f"Ошибка хранилища: {e}", file=sys.stderr)
        return EXIT_ERROR

    try:
        repository.migrate()
    except RuntimeError as e:
        print(f"Схема не готова: {e}", file=sys.stderr)
        return EXIT_ERROR

    handlers = {
        "collect": _cmd_collect,
        "enrich": _cmd_enrich,
        "export": _cmd_export,
        "stats": _cmd_stats,
    }

    try:
        return handlers[args.command](args, profiles, repository)
    except ProfileError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return EXIT_ERROR
    finally:
        repository.close()


# ── команды ──

def _cmd_collect(args, profiles, repository) -> int:
    seed_records = None
    if args.from_file:
        path = Path(args.from_file)
        if not path.exists():
            print(f"Файл не найден: {path}", file=sys.stderr)
            return EXIT_USAGE
        try:
            seed_records = parse_seed_file(path)
        except (ValueError, RuntimeError, FileNotFoundError) as exc:
            print(f"Ошибка файла-сида: {exc}", file=sys.stderr)
            return EXIT_USAGE

    pipeline = LeadsPipeline(repository, profiles)
    result = pipeline.collect(
        args.profile, sources=args.source, seed_records=seed_records
    )
    print(result.summary())
    return EXIT_OK if result.status == "success" else EXIT_ERROR


def _cmd_enrich(args, profiles, repository) -> int:
    pipeline = LeadsPipeline(repository, profiles)
    result = pipeline.enrich(
        profile_name=args.profile, limit=args.limit, retry_failed=args.retry_failed
    )
    print(result.summary())
    return EXIT_OK


def _cmd_export(args, profiles, repository) -> int:
    if args.profile:
        profiles.get(args.profile)  # проверяем, что профиль существует

    companies = repository.iter_companies(profile=args.profile)
    blacklist = Blacklist.load()

    if args.include_personal:
        print(
            "ВНИМАНИЕ: включены персональные адреса. По PIPL (закон КНР о "
            "персональных данных) рассылка на именные ящики без согласия "
            "субъекта несёт правовые риски. См. docs/LEADS.md."
        )

    result = export_csv(
        companies,
        out_path=args.out,
        blacklist=blacklist,
        include_personal=args.include_personal,
        profiles=profiles,
        encoding=args.encoding or DEFAULT_ENCODING,
    )
    print(result.summary())
    return EXIT_OK


def _cmd_stats(args, profiles, repository) -> int:
    data = repository.stats(profile=args.profile)

    print(f"Хранилище: {data['storage']}")
    print(f"Компаний: {data['companies']} (с почтами: {data['companies_with_emails']})")
    print(
        f"Почт: {data['emails']} "
        f"(ролевых {data['emails_role']}, персональных {data['emails_personal']})"
    )

    _print_breakdown("По профилям", data.get("by_profile"))
    _print_breakdown("По провинциям", data.get("by_province"), top=15)
    _print_breakdown("По статусу обогащения", data.get("by_enrich_status"))
    return EXIT_OK


def _print_breakdown(title: str, values: dict[str, int] | None, top: int = 0) -> None:
    if not values:
        return
    print(f"\n{title}:")
    items = sorted(values.items(), key=lambda kv: -kv[1])
    shown = items[:top] if top else items
    for name, count in shown:
        print(f"  {name:<28} {count}")
    if top and len(items) > top:
        print(f"  … и ещё {len(items) - top}")


__all__ = ["main", "build_parser", "DISABLED_MESSAGE"]
