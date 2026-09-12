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
from collections.abc import Sequence
from pathlib import Path

from engine.observability.logger import setup_logging
from leads.blacklist import Blacklist
from leads.campaigns import CampaignError, load_campaigns
from leads.outreach import CrmBridge
from leads.export import DEFAULT_ENCODING, export_csv
from leads.gis2 import collect_gis2
from leads.pipeline import LeadsPipeline
from leads.profiles import ProfileError, load_profiles
from leads.scoring import heat_breakdown, score_heat
from leads.seed import parse_seed_file
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
            "  python -m leads campaign list\n"
            "  python -m leads campaign run omsk_machines\n"
        ),
    )
    parser.add_argument("--log-level", default="INFO", help="Уровень логирования (по умолчанию INFO)")
    parser.add_argument(
        "--profiles-config",
        default="",
        help="Путь к YAML с профилями (по умолчанию config/leads_profiles.yaml)",
    )
    parser.add_argument(
        "--campaigns-config",
        default="",
        help="Путь к YAML с кампаниями (по умолчанию config/lead_campaigns.yaml)",
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

    score = sub.add_parser("score", help="Оценить лидов по теплоте (cold/warm/hot)")
    score.add_argument("--profile", default="", help="Ограничить профилем")
    score.add_argument(
        "--countries",
        default="",
        help="Целевые страны через запятую (перекрывает страны профиля)",
    )
    score.add_argument("--out", default="", help="Выгрузить отчёт в CSV (опционально)")
    score.add_argument("--top", type=int, default=20, help="Показать N самых горячих лидов")


    campaign = sub.add_parser("campaign", help="Кампании лидогенерации (ниша × гео)")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)

    campaign_sub.add_parser("list", help="Показать доступные кампании")
    campaign_run = campaign_sub.add_parser("run", help="Собрать лидов по кампании (2ГИС)")
    campaign_run.add_argument("name", help="Имя кампании из lead_campaigns.yaml")
    campaign_run.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="Максимум записей с одного URL 2ГИС (0 — лимит parser-2gis)",
    )
    campaign_run.add_argument(
        "--parser-bin",
        default="parser-2gis",
        help="Путь к CLI parser-2gis (по умолчанию parser-2gis в PATH)",
    )

    sync_crm = sub.add_parser(
        "sync-crm",
        help="Синхронизировать обогащённые лиды в CRM и создать черновики КП",
    )
    sync_crm.add_argument("--profile", default="", help="Ограничить профилем/кампанией")
    sync_crm.add_argument(
        "--limit", type=int, default=0, help="Максимум компаний за прогон"
    )
    sync_crm.add_argument(
        "--no-llm",
        action="store_true",
        help="Не использовать LLM: черновики по детерминированному шаблону",
    )

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
        "score": _cmd_score,
        "campaign": _cmd_campaign,
        "sync-crm": _cmd_sync_crm,
    }

    try:
        return handlers[args.command](args, profiles, repository)
    except (ProfileError, CampaignError) as e:
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


def _cmd_score(args, profiles, repository) -> int:
    """Оценить лидов по теплоте и вывести разбивку cold/warm/hot."""
    companies = repository.iter_companies(profile=args.profile or None)

    countries: set[str] | None = None
    if args.countries:
        countries = {c.strip() for c in args.countries.split(",") if c.strip()}
    elif args.profile:
        countries = set(profiles.get(args.profile).countries)

    breakdown = heat_breakdown(companies, countries=countries)
    print(f"Всего лидов: {len(companies)}")
    print(
        f"Горячих: {breakdown['hot']}, тёплых: {breakdown['warm']}, "
        f"холодных: {breakdown['cold']}"
    )
    if countries:
        print(f"Целевые страны: {', '.join(sorted(countries))}")

    ordered = sorted(
        ((score_heat(c, countries=countries), c) for c in companies),
        key=lambda pair: -pair[0].score,
    )
    shown = min(args.top, len(ordered))
    print(f"\nТоп-{shown} по баллу:")
    for heat, company in ordered[: args.top]:
        contact = company.emails[0].email if company.emails else "—"
        print(
            f"  [{heat.heat:<4} {heat.score:>2}] {company.display_name:<38} "
            f"{company.country or '—':<12} {contact}"
        )

    if args.out:
        _write_scored_csv(ordered, args.out)

    return EXIT_OK


def _write_scored_csv(scored, path: str) -> None:
    """Сохранить отчёт по теплоте в CSV (utf-8-sig для Excel)."""
    import csv

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "name", "country", "province", "city", "website",
                "emails", "phones", "wechat", "whatsapp",
                "heat", "score", "reasons",
            ]
        )
        for heat, company in scored:
            writer.writerow(
                [
                    company.display_name,
                    company.country,
                    company.province,
                    company.city,
                    company.website,
                    ", ".join(e.email for e in company.emails),
                    ", ".join(company.phones),
                    company.wechat,
                    company.whatsapp,
                    heat.heat,
                    heat.score,
                    ", ".join(heat.reasons),
                ]
            )
    print(f"Отчёт сохранён: {path}")



def _cmd_campaign(args, profiles, repository) -> int:
    """Команды слоя кампаний: list и run."""
    config = load_campaigns(args.campaigns_config or None)
    if args.campaign_command == "list":
        for name in config.names:
            campaign = config.campaigns[name]
            geo = ", ".join(campaign.countries) or "—"
            print(f"{name:<32} {campaign.niche_name:<40} {geo}")
        return EXIT_OK

    campaign = config.get(args.name)
    targets = campaign.to_gis2_targets()
    if not targets:
        print(
            "Кампания без целей 2ГИС: в секции gis2 не заданы города/рубрики. "
            "Нечего обходить.",
            file=sys.stderr,
        )
        return EXIT_OK

    print(f"Кампания: {campaign.name} ({campaign.niche_name})")
    print(f"Целей 2ГИС: {len(targets)} (город × рубрики)")
    inserted, updated = collect_gis2(
        targets,
        repository,
        profile=campaign.name,
        parser_bin=args.parser_bin,
        max_records=args.max_records,
    )
    print(f"Компаний: вставлено {inserted}, обновлено {updated}")
    print("Дальше: python -m leads enrich  (обход сайтов, добор почт)")
    return EXIT_OK



def _cmd_sync_crm(args, profiles, repository) -> int:
    """Синхронизировать лиды в CRM (crm_leads) и создать черновики КП."""
    companies = repository.iter_companies(
        profile=args.profile or None,
        enrich_status="done",
        limit=args.limit,
    )
    if not companies:
        print("Нет обогащённых компаний (enrich_status=done) — сначала python -m leads enrich")
        return EXIT_OK

    llm = None
    if not args.no_llm:
        from leads.llm import AgentRouterClient

        llm = AgentRouterClient()
        if not llm.api_key:
            print("AGENT_ROUTER_API_KEY не задан — черновики по шаблону (--no-llm режим)")
            llm = None

    from shared.config import supabase_key, supabase_url

    if not supabase_url() or not supabase_key():
        print("SUPABASE_URL/SUPABASE_KEY не заданы — CRM-мост требует Supabase", file=sys.stderr)
        return EXIT_ERROR

    from supabase import create_client

    bridge = CrmBridge(client=create_client(supabase_url(), supabase_key()), llm=llm)

    created = bridge.sync_leads(companies, profile=args.profile)
    tasks = bridge.draft_email_tasks(companies)
    print(f"CRM-лидов создано: {created}")
    print(f"Черновиков КП создано: {len(tasks)} (статус draft — отправка после вашего «ОК»)")
    if llm is not None:
        print(f"LLM токенов израсходовано: {llm.tokens_used}")
    return EXIT_OK


__all__ = ["DISABLED_MESSAGE", "build_parser", "main"]
