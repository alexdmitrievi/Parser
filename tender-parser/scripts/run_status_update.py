#!/usr/bin/env python3
"""Пометка expired и проверка статуса ЕИС для активных тендеров.

Требует SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY (или SUPABASE_KEY) в env.
Запуск из каталога tender-parser:
    python scripts/run_status_update.py
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import supabase_key, supabase_url
from pipeline.status_updater import fetch_eis_status, mark_expired_by_deadline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    url, key = supabase_url(), supabase_key()
    if not url or not key:
        logger.error("Supabase not configured (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY)")
        return 1
    from supabase import create_client

    cli = create_client(url, key)
    res = (
        cli.table("tenders")
        .select("id, registry_number, status, submission_deadline, source_platform")
        .eq("status", "active")
        .limit(2000)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    expired = mark_expired_by_deadline(rows)
    logger.info(f"Found {len(expired)} expired tenders out of {len(rows)} active")
    for u in expired:
        try:
            cli.table("tenders").update({"status": u["status"]}).eq("id", u["id"]).execute()
        except Exception as e:
            logger.warning(f"Failed to update {u['id']}: {e}")
    logger.info(f"Marked {len(expired)} tenders as expired")
    logger.info("status update done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
