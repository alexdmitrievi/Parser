"""Healthcheck мониторинга: БД доступна, последний цикл свежий.

Использование:
    python scripts/healthcheck.py            # человекочитаемый вывод
    python scripts/healthcheck.py --quiet    # только exit code (0 = OK)

Exit codes: 0 — OK, 1 — цикл устарел/падает, 2 — БД недоступна.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.env import load_dotenv  # noqa: E402

load_dotenv()

MAX_CYCLE_AGE_HOURS = float(os.environ.get("HEALTHCHECK_MAX_AGE_HOURS", "5"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    def report(msg: str) -> None:
        if not args.quiet:
            print(msg)

    try:
        from engine.persistence.postgres_repo import PostgresTenderRepository
        repo = PostgresTenderRepository()
        repo.ensure_schema()
    except Exception as e:
        report(f"FAIL: database unreachable: {e}")
        return 2

    try:
        last = repo.get_state("last_cycle")
        if not last:
            report("WARN: no cycles have run yet")
            return 1

        finished = datetime.fromisoformat(last["finished_at"])
        age = datetime.now(timezone.utc) - finished
        if age > timedelta(hours=MAX_CYCLE_AGE_HOURS):
            report(f"FAIL: last cycle finished {age} ago (> {MAX_CYCLE_AGE_HOURS}h)")
            return 1

        failures = {
            key: info for key, info in (last.get("summary") or {}).items()
            if isinstance(info, dict) and (info.get("failed") or info.get("error"))
        }
        if failures:
            report(f"WARN: last cycle had failures: {failures}")
            return 1

        report(f"OK: last cycle finished {age} ago, summary: {last.get('summary')}")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
