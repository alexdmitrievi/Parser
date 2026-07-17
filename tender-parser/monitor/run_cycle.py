"""Один цикл мониторинга закупок. Запускается systemd-таймером раз в 120 минут.

Шаги:
    1. Перечитать config/filters.yaml (правки применяются без рестарта).
    2. FTP ЕИС (44-ФЗ + 223-ФЗ, Омская и Новосибирская обл.) → PostgreSQL.
    3. Отправить карточки по новым закупкам, прошедшим фильтры.
    4. Собрать протоколы итогов (без уведомлений).
    5. Сервисные алерты: источник/цикл падает два прохода подряд → Telegram.

Запуск вручную:
    python -m monitor.run_cycle
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.env import load_dotenv  # noqa: E402

load_dotenv()

from engine.persistence.postgres_repo import PostgresTenderRepository  # noqa: E402
from engine.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from engine.sources.tenders.eis_ftp import make_eis_ftp_adapters  # noqa: E402
from monitor.business_filter import BusinessFilter  # noqa: E402
from monitor.notifier import notify_new_tenders  # noqa: E402
from monitor.protocols import ProtocolCollector  # noqa: E402
from monitor.telegram_client import send_message  # noqa: E402

logger = logging.getLogger("monitor.cycle")

ALERT_THRESHOLD = 2  # неудачных проходов подряд до алерта
ALERT_REPEAT_EVERY = 12  # повторный алерт каждые N неудачных проходов


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handlers: list[logging.Handler] = [logging.StreamHandler()]  # → journald
    log_file = os.environ.get("MONITOR_LOG_FILE", "")
    if log_file:
        from logging.handlers import RotatingFileHandler
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        handlers.append(RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
        ))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _track_failures(repo: PostgresTenderRepository, key: str, failed: bool,
                    alert_text: str) -> None:
    """Счётчик неудач подряд + алерт при достижении порога."""
    state_key = f"failures:{key}"
    count = int(repo.get_state(state_key, 0) or 0)
    if failed:
        count += 1
        repo.set_state(state_key, count)
        if count == ALERT_THRESHOLD or (
            count > ALERT_THRESHOLD and (count - ALERT_THRESHOLD) % ALERT_REPEAT_EVERY == 0
        ):
            send_message(f"⚠️ <b>Мониторинг закупок</b>\n{alert_text}\n"
                         f"Неудачных проходов подряд: {count}")
    elif count:
        repo.set_state(state_key, 0)
        if count >= ALERT_THRESHOLD:
            send_message(f"✅ <b>Мониторинг закупок</b>\nИсточник «{key}» снова работает.")


def run_cycle() -> int:
    """Полный цикл. Возвращает exit code для systemd."""
    started = datetime.now(timezone.utc)
    logger.info("=== Monitoring cycle started ===")

    repo = PostgresTenderRepository()
    repo.ensure_schema()

    try:
        business_filter = BusinessFilter.load()
    except Exception as e:
        logger.error(f"filters.yaml is broken: {e} — cycle aborted")
        _track_failures(repo, "filters", True,
                        f"Не удалось прочитать config/filters.yaml: {e}")
        return 1
    _track_failures(repo, "filters", False, "")

    orchestrator = PipelineOrchestrator(repository=repo)
    tmp_dir = os.environ.get("MONITOR_TMP_DIR") or None
    if tmp_dir:
        os.makedirs(tmp_dir, exist_ok=True)

    summary: dict[str, dict] = {}
    for adapter in make_eis_ftp_adapters(repo, tmp_dir=tmp_dir):
        source_id = adapter.source_id
        with adapter:
            stats = orchestrator.run_source(adapter)
            # Неудача: ошибки пайплайна, ни одного скачанного архива при
            # наличии ошибок сети, ЛИБО архивы скачаны, но ни одно извещение
            # не разобрано — признак смены схемы XML (тихая деградация).
            failed = (
                stats.errors > 0
                or (stats.total_fetched == 0 and stats.fetch_errors > 0)
                or (stats.total_fetched > 0 and stats.total_parsed == 0)
            )
            if not failed:
                adapter.commit_processed()
        summary[source_id] = {
            "fetched": stats.total_fetched,
            "parsed": stats.total_parsed,
            "inserted": stats.inserted,
            "updated": stats.updated,
            "errors": stats.errors,
            "fetch_errors": stats.fetch_errors,
            "failed": failed,
        }
        _track_failures(
            repo, source_id, failed,
            f"Источник «{source_id}» (FTP ЕИС) недоступен или падает.",
        )

    # Этап 5: коммерческие площадки (B2B-Center, Фабрикант) — включаются
    # флагом COMMERCIAL_SOURCES=1 после приёмки этапов 1–4.
    if os.environ.get("COMMERCIAL_SOURCES", "0") == "1":
        from engine.sources.tenders.b2b_center import B2B_CENTER_CONFIG, B2BCenterSourceAdapter
        from engine.sources.tenders.fabrikant import FABRIKANT_CONFIG, FabrikantSourceAdapter

        for cfg, cls in ((B2B_CENTER_CONFIG, B2BCenterSourceAdapter),
                         (FABRIKANT_CONFIG, FabrikantSourceAdapter)):
            adapter = cls(cfg)
            with adapter:
                stats = orchestrator.run_source(adapter)
            failed = stats.errors > 0
            summary[cfg.source_id] = {
                "fetched": stats.total_fetched,
                "parsed": stats.total_parsed,
                "inserted": stats.inserted,
                "updated": stats.updated,
                "failed": failed,
            }
            _track_failures(
                repo, cfg.source_id, failed,
                f"Коммерческая площадка «{cfg.source_id}» недоступна или падает.",
            )

    # Уведомления по новым подходящим закупкам
    try:
        notify_stats = notify_new_tenders(repo, business_filter)
        summary["notifier"] = dict(notify_stats)
        # Telegram не доставляет карточки → алерт после 2 циклов подряд,
        # пока 48-часовое окно ретраев не истекло молча.
        notify_failed = notify_stats["matched"] > notify_stats["sent"]
        _track_failures(
            repo, "notifier", notify_failed,
            "Карточки не доставляются в Telegram (проверьте токен/сеть) — "
            "неотправленные закупки будут ретраиться 48 часов.",
        )
    except Exception as e:
        logger.error(f"Notifier failed: {e}", exc_info=True)
        summary["notifier"] = {"error": str(e)}
        _track_failures(repo, "notifier", True, f"Модуль уведомлений упал: {e}")

    # Протоколы итогов — только копим в БД
    try:
        proto_stats = ProtocolCollector(repo, tmp_dir=tmp_dir).collect()
        summary["protocols"] = dict(proto_stats)
    except Exception as e:
        logger.error(f"Protocol collection failed: {e}", exc_info=True)
        summary["protocols"] = {"error": str(e)}

    repo.cleanup_processed_archives()
    _track_failures(repo, "cycle", False, "")
    repo.set_state("last_cycle", {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    })

    logger.info(f"=== Cycle done: {summary} ===")
    return 0


def main() -> int:
    _configure_logging()
    try:
        return run_cycle()
    except Exception as e:
        logger.error(f"Cycle crashed: {e}\n{traceback.format_exc()}")
        # Алерт о падении цикла (два подряд) — через отдельное подключение,
        # т.к. основной repo мог быть причиной падения.
        try:
            repo = PostgresTenderRepository()
            repo.ensure_schema()
            _track_failures(repo, "cycle", True, f"Цикл мониторинга упал: {e}")
        except Exception:
            # БД недоступна — шлём алерт напрямую, без счётчика
            send_message(f"🔥 <b>Мониторинг закупок</b>\nЦикл упал, БД недоступна: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
