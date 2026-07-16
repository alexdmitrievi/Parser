"""Local PostgreSQL implementation of TenderRepository for the VPS monitor.

Replaces Supabase for the single-user production monitoring loop:
the database lives next to the parser, is backed up with pg_dump, and
has no external-service dependency. The grants (funding) part of the
project keeps using Supabase and is not affected.

Connection settings come from the DATABASE_URL env var, e.g.:
    postgresql://tender:secret@localhost:5432/tender_monitor
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from engine.persistence.repository import TenderRepository

logger = logging.getLogger("engine.persistence.postgres")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenders (
    id BIGSERIAL PRIMARY KEY,
    source_platform TEXT NOT NULL,
    registry_number TEXT NOT NULL,
    law_type TEXT,
    purchase_method TEXT,
    title TEXT NOT NULL,
    description TEXT,
    customer_name TEXT,
    customer_inn TEXT,
    customer_region TEXT,
    okpd2_codes TEXT[] DEFAULT '{}',
    nmck NUMERIC,
    currency TEXT DEFAULT 'RUB',
    application_guarantee NUMERIC,
    contract_guarantee NUMERIC,
    publish_date TIMESTAMPTZ,
    submission_deadline TIMESTAMPTZ,
    auction_date TIMESTAMPTZ,
    status TEXT DEFAULT 'active',
    original_url TEXT,
    niche_tags TEXT[] DEFAULT '{}',
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source_platform, registry_number)
);

CREATE INDEX IF NOT EXISTS idx_tenders_created_at ON tenders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_registry ON tenders (registry_number);

-- Инкрементальность FTP ЕИС: какие архивы уже обработаны
CREATE TABLE IF NOT EXISTS eis_processed_archives (
    archive_path TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT now()
);

-- Какие тендеры уже отправлены в Telegram (защита от дублей уведомлений)
CREATE TABLE IF NOT EXISTS notified_tenders (
    registry_number TEXT PRIMARY KEY,
    notified_at TIMESTAMPTZ DEFAULT now()
);

-- Протоколы подведения итогов (этап 4) — только копим, не уведомляем
CREATE TABLE IF NOT EXISTS protocols (
    id BIGSERIAL PRIMARY KEY,
    registry_number TEXT NOT NULL UNIQUE,
    law_type TEXT,
    region TEXT,
    winner_name TEXT,
    winner_inn TEXT,
    winner_price NUMERIC,
    nmck NUMERIC,
    reduction_pct NUMERIC,
    participants_count INTEGER,
    protocol_date TIMESTAMPTZ,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Состояние циклов мониторинга: для сервисных алертов после 2 неудач подряд
CREATE TABLE IF NOT EXISTS monitor_state (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""

_JSON_FIELDS = ("raw_data", "documents_urls", "contact_info")
_DROP_FIELDS = ("documents_urls", "contact_info", "sources")  # не храним в локальной схеме
_ARRAY_FIELDS = ("okpd2_codes", "niche_tags")
_DT_FIELDS = ("publish_date", "submission_deadline", "auction_date")

_TENDER_COLUMNS = (
    "source_platform", "registry_number", "law_type", "purchase_method",
    "title", "description", "customer_name", "customer_inn", "customer_region",
    "okpd2_codes", "nmck", "currency", "application_guarantee",
    "contract_guarantee", "publish_date", "submission_deadline",
    "auction_date", "status", "original_url", "niche_tags", "raw_data",
)


class PostgresTenderRepository(TenderRepository):
    """Postgres-backed tender repository + monitor state storage."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or os.environ.get("DATABASE_URL", "")
        if not self._dsn:
            raise RuntimeError("DATABASE_URL is not set")
        self._conn = None

    # --------------- connection ---------------

    def _get_conn(self):
        import psycopg

        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    def ensure_schema(self) -> None:
        """Create tables if missing. Safe to call on every cycle."""
        with self._get_conn().cursor() as cur:
            cur.execute(SCHEMA_SQL)

    # --------------- TenderRepository interface ---------------

    def upsert_batch(
        self,
        records: list[dict[str, Any]],
        conflict_keys: tuple[str, ...] = ("source_platform", "registry_number"),
        batch_size: int = 200,
    ) -> int:
        if not records:
            return 0

        seen: set[tuple] = set()
        rows: list[dict] = []
        for rec in records:
            key = tuple(str(rec.get(k, "")) for k in conflict_keys)
            if key in seen:
                continue
            seen.add(key)
            rows.append(self._prepare_row(rec))

        cols = _TENDER_COLUMNS
        placeholders = ", ".join(f"%({c})s" for c in cols)
        update_cols = [c for c in cols if c not in conflict_keys]
        set_clause = ", ".join(
            f"{c} = COALESCE(EXCLUDED.{c}, tenders.{c})" for c in update_cols
        )
        sql = (
            f"INSERT INTO tenders ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(conflict_keys)}) "
            f"DO UPDATE SET {set_clause}, updated_at = now()"
        )

        conn = self._get_conn()
        total = 0
        with conn.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                cur.executemany(sql, rows[i : i + batch_size])
                total += cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(rows[i : i + batch_size])
        logger.info(f"Upserted {total} tenders into local PostgreSQL")
        return total

    def _prepare_row(self, rec: dict[str, Any]) -> dict[str, Any]:
        row = {k: v for k, v in rec.items() if k not in _DROP_FIELDS}
        for f in _DT_FIELDS:
            v = row.get(f)
            if isinstance(v, datetime):
                row[f] = v.isoformat()
        raw = row.get("raw_data")
        if raw is not None and not isinstance(raw, str):
            row["raw_data"] = json.dumps(raw, ensure_ascii=False, default=str)
        for col in _TENDER_COLUMNS:
            row.setdefault(col, None)
        for f in _ARRAY_FIELDS:
            if row.get(f) is None:
                row[f] = []
        if row.get("currency") is None:
            row["currency"] = "RUB"
        if row.get("status") is None:
            row["status"] = "active"
        return {k: row[k] for k in _TENDER_COLUMNS}

    def fetch_existing_by_registry(
        self,
        registry_numbers: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not registry_numbers:
            return {}
        conn = self._get_conn()
        result: dict[str, dict[str, Any]] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenders WHERE registry_number = ANY(%s)",
                (registry_numbers,),
            )
            columns = [d.name for d in cur.description]
            for values in cur.fetchall():
                row = dict(zip(columns, values))
                if row.get("nmck") is not None:
                    row["nmck"] = float(row["nmck"])
                result[row["registry_number"]] = row
        return result

    def fetch_record_by_id(self, record_id: str) -> Optional[dict[str, Any]]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tenders WHERE id = %s", (record_id,))
            row = cur.fetchone()
            if not row:
                return None
            columns = [d.name for d in cur.description]
            return dict(zip(columns, row))

    def update_record(self, record_id: str, updates: dict[str, Any]) -> bool:
        if not updates:
            return True
        conn = self._get_conn()
        set_clause = ", ".join(f"{k} = %({k})s" for k in updates)
        params = {**updates, "_id": record_id}
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE tenders SET {set_clause}, updated_at = now() WHERE id = %(_id)s",
                    params,
                )
            return True
        except Exception as e:
            logger.error(f"Update record {record_id} failed: {e}")
            return False

    def store_snapshot(
        self,
        registry_number: str,
        source_platform: str,
        snapshot: dict[str, Any],
    ) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tenders SET raw_data = %s WHERE registry_number = %s AND source_platform = %s",
                (json.dumps(snapshot, ensure_ascii=False, default=str),
                 registry_number, source_platform),
            )

    # --------------- FTP incremental state ---------------

    def filter_new_archives(self, archive_paths: list[str]) -> list[str]:
        """Return only the archives that were never processed before."""
        if not archive_paths:
            return []
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT archive_path FROM eis_processed_archives WHERE archive_path = ANY(%s)",
                (archive_paths,),
            )
            done = {r[0] for r in cur.fetchall()}
        return [p for p in archive_paths if p not in done]

    def mark_archives_processed(self, archive_paths: list[str], source_id: str) -> None:
        if not archive_paths:
            return
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO eis_processed_archives (archive_path, source_id) "
                "VALUES (%s, %s) ON CONFLICT (archive_path) DO NOTHING",
                [(p, source_id) for p in archive_paths],
            )

    def cleanup_processed_archives(self, keep_days: int = 90) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM eis_processed_archives WHERE processed_at < now() - make_interval(days => %s)",
                (keep_days,),
            )

    # --------------- notifications ---------------

    def fetch_unnotified_tenders(self, since_hours: int = 48) -> list[dict[str, Any]]:
        """Fresh tenders that were never sent to Telegram."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.* FROM tenders t
                LEFT JOIN notified_tenders n ON n.registry_number = t.registry_number
                WHERE n.registry_number IS NULL
                  AND t.created_at > now() - make_interval(hours => %s)
                ORDER BY t.created_at
                """,
                (since_hours,),
            )
            columns = [d.name for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]
        for row in rows:
            for f in ("nmck", "application_guarantee", "contract_guarantee"):
                if row.get(f) is not None:
                    row[f] = float(row[f])
        return rows

    def mark_notified(self, registry_numbers: list[str]) -> None:
        if not registry_numbers:
            return
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO notified_tenders (registry_number) VALUES (%s) "
                "ON CONFLICT (registry_number) DO NOTHING",
                [(r,) for r in registry_numbers],
            )

    # --------------- protocols (этап 4) ---------------

    def upsert_protocol(self, protocol: dict[str, Any]) -> None:
        conn = self._get_conn()
        cols = ("registry_number", "law_type", "region", "winner_name",
                "winner_inn", "winner_price", "nmck", "reduction_pct",
                "participants_count", "protocol_date", "raw_data")
        row = {c: protocol.get(c) for c in cols}
        if row["raw_data"] is not None and not isinstance(row["raw_data"], str):
            row["raw_data"] = json.dumps(row["raw_data"], ensure_ascii=False, default=str)
        if isinstance(row.get("protocol_date"), datetime):
            row["protocol_date"] = row["protocol_date"].isoformat()
        placeholders = ", ".join(f"%({c})s" for c in cols)
        update = ", ".join(
            f"{c} = COALESCE(EXCLUDED.{c}, protocols.{c})"
            for c in cols if c != "registry_number"
        )
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO protocols ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT (registry_number) DO UPDATE SET {update}",
                row,
            )

    def fetch_filtered_registry_numbers(self) -> set[str]:
        """Registry numbers of tenders that were notified (passed business filters)."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT registry_number FROM notified_tenders")
            return {r[0] for r in cur.fetchall()}

    def stats_last_days(self, days: int = 30) -> dict[str, Any]:
        """Aggregate stats for /stats bot command."""
        conn = self._get_conn()
        out: dict[str, Any] = {}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*),
                       count(*) FILTER (WHERE n.registry_number IS NOT NULL)
                FROM tenders t
                LEFT JOIN notified_tenders n ON n.registry_number = t.registry_number
                WHERE t.created_at > now() - make_interval(days => %s)
                """,
                (days,),
            )
            total, matched = cur.fetchone()
            out["tenders_total"] = total
            out["tenders_matched"] = matched

            cur.execute(
                """
                SELECT tag, count(*) FROM (
                    SELECT unnest(niche_tags) AS tag FROM tenders
                    WHERE created_at > now() - make_interval(days => %s)
                ) s GROUP BY tag ORDER BY count(*) DESC
                """,
                (days,),
            )
            out["by_niche"] = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute(
                """
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY reduction_pct),
                       count(*)
                FROM protocols
                WHERE created_at > now() - make_interval(days => %s)
                  AND reduction_pct IS NOT NULL
                """,
                (days,),
            )
            median_red, proto_count = cur.fetchone()
            out["median_reduction_pct"] = float(median_red) if median_red is not None else None
            out["protocols_count"] = proto_count

            cur.execute(
                """
                SELECT region, winner_name, winner_inn, count(*) AS wins,
                       sum(winner_price) AS total_price
                FROM protocols
                WHERE created_at > now() - make_interval(days => %s)
                  AND winner_name IS NOT NULL
                GROUP BY region, winner_name, winner_inn
                ORDER BY wins DESC, total_price DESC NULLS LAST
                LIMIT 5
                """,
                (days,),
            )
            out["top_winners"] = [
                {
                    "region": r[0], "winner_name": r[1], "winner_inn": r[2],
                    "wins": r[3],
                    "total_price": float(r[4]) if r[4] is not None else None,
                }
                for r in cur.fetchall()
            ]
        return out

    # --------------- monitor state (алерты) ---------------

    def get_state(self, key: str, default: Any = None) -> Any:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM monitor_state WHERE key = %s", (key,))
            row = cur.fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value: Any) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO monitor_state (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, json.dumps(value, ensure_ascii=False, default=str)),
            )
