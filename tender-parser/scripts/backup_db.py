"""Database backup — dumps all public tables to JSON via Supabase REST API."""
from __future__ import annotations

import json
import logging
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from shared.config import supabase_key, supabase_url
from shared.db import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("backup")

PUBLIC_TABLES = [
    "tenders",
    "funding_programs",
    "subscriptions",
    "bot_users",
    "notifications_log",
    "tender_snapshots",
]


def dump_table(name: str, output_dir: Path) -> int:
    """Dump all rows from a table to a JSON file. Returns row count."""
    db = get_db()
    rows: list[dict] = []
    per_page = 1000
    page = 0

    while True:
        result = (
            db.table(name)
            .select("*", count="exact")
            .range(page * per_page, (page + 1) * per_page - 1)
            .execute()
        )
        data = result.data or []
        if not data:
            break
        rows.extend(data)
        page += 1
        if len(data) < per_page:
            break

    filepath = output_dir / f"{name}.json"
    filepath.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info(f"  {name}: {len(rows)} rows → {filepath.stat().st_size:,} bytes")
    return len(rows)


def main() -> int:
    url = supabase_url()
    key = supabase_key()
    if not url or not key:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — aborting")
        return 1

    logger.info(f"Starting backup from {url}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(os.environ.get("BACKUP_DIR", ".")) / f"backup_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for table in PUBLIC_TABLES:
        try:
            count = dump_table(table, out_dir)
            total += count
        except Exception as e:
            logger.error(f"  {table}: FAILED — {e}")

    # Create zip
    zip_path = out_dir.parent / f"{out_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.rglob("*.json"):
            zf.write(f, f.relative_to(out_dir.parent))
    zip_size = zip_path.stat().st_size

    # Cleanup individual JSONs
    import shutil

    shutil.rmtree(out_dir)

    logger.info(f"Backup complete: {zip_path.name} ({zip_size:,} bytes, {total} total rows)")
    print(f"::set-output name=zip_path::{zip_path}")
    print(f"::set-output name=zip_name::{zip_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
