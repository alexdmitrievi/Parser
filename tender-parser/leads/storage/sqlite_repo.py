"""SQLite-хранилище лидов — используется по умолчанию.

Локальный файл (``LEADS_DB_PATH``, по умолчанию ``data/leads.sqlite3``) даёт
работающие ``collect``/``enrich``/``export``/``stats`` без облачных ключей.
Схема повторяет ``scripts/migration_leads.sql`` — тот же набор таблиц и
уникальных ключей, что и в Supabase.

Миграция идемпотентна: ``CREATE TABLE IF NOT EXISTS``, повторный вызов ничего
не ломает и не теряет данные.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.observability.logger import get_logger
from leads.dedup import company_key
from leads.models import LeadCompany, LeadEmail, utcnow
from leads.storage.base import TABLE_COMPANIES, TABLE_EMAILS, TABLE_RUNS, LeadsRepository

logger = get_logger("leads.storage.sqlite")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE_COMPANIES} (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key       TEXT    NOT NULL UNIQUE,
    company_name_en TEXT    NOT NULL DEFAULT '',
    company_name_zh TEXT    NOT NULL DEFAULT '',
    province        TEXT    NOT NULL DEFAULT '',
    city            TEXT    NOT NULL DEFAULT '',
    country         TEXT    NOT NULL DEFAULT '',
    website         TEXT    NOT NULL DEFAULT '',
    domain          TEXT    NOT NULL DEFAULT '',
    phones          TEXT    NOT NULL DEFAULT '[]',
    wechat          TEXT    NOT NULL DEFAULT '',
    whatsapp        TEXT    NOT NULL DEFAULT '',
    matched_keywords TEXT   NOT NULL DEFAULT '[]',
    profile         TEXT    NOT NULL DEFAULT '',
    industry_guess  TEXT    NOT NULL DEFAULT '',
    activity        TEXT    NOT NULL DEFAULT '',
    offers          TEXT    NOT NULL DEFAULT '[]',
    requests        TEXT    NOT NULL DEFAULT '[]',
    source_url      TEXT    NOT NULL DEFAULT '',
    source_name     TEXT    NOT NULL DEFAULT '',
    enrich_status   TEXT    NOT NULL DEFAULT 'pending',
    enrich_note     TEXT    NOT NULL DEFAULT '',
    first_seen      TEXT    NOT NULL,
    last_seen       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_companies_profile  ON {TABLE_COMPANIES}(profile);
CREATE INDEX IF NOT EXISTS idx_leads_companies_province ON {TABLE_COMPANIES}(province);
CREATE INDEX IF NOT EXISTS idx_leads_companies_status   ON {TABLE_COMPANIES}(enrich_status);
CREATE INDEX IF NOT EXISTS idx_leads_companies_domain   ON {TABLE_COMPANIES}(domain);

CREATE TABLE IF NOT EXISTS {TABLE_EMAILS} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL REFERENCES {TABLE_COMPANIES}(id) ON DELETE CASCADE,
    email       TEXT    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'role',
    source_url  TEXT    NOT NULL DEFAULT '',
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL,
    UNIQUE(company_id, email)
);

CREATE INDEX IF NOT EXISTS idx_leads_emails_company ON {TABLE_EMAILS}(company_id);
CREATE INDEX IF NOT EXISTS idx_leads_emails_kind    ON {TABLE_EMAILS}(kind);

CREATE TABLE IF NOT EXISTS {TABLE_RUNS} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    command     TEXT    NOT NULL,
    profile     TEXT    NOT NULL DEFAULT '',
    found       INTEGER NOT NULL DEFAULT 0,
    inserted    INTEGER NOT NULL DEFAULT 0,
    updated     INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'success',
    note        TEXT    NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT    NOT NULL
);
"""


def _parse_dt(value: Any) -> datetime:
    """Разобрать ISO-строку; при неудаче — текущее время."""
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return utcnow()


class SqliteLeadsRepository(LeadsRepository):
    """Локальное хранилище лидов на SQLite."""

    def __init__(self, path: str = "data/leads.sqlite3"):
        self.path = path
        self._conn: sqlite3.Connection | None = None

    # ── подключение ──

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            target = Path(self.path)
            if target.parent and str(target.parent) not in ("", "."):
                target.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(target))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def migrate(self) -> None:
        """Создать схему, если её нет. Безопасно вызывать многократно."""
        conn = self._connect()
        conn.executescript(SCHEMA)
        self._ensure_columns(conn)
        conn.commit()
        logger.debug(f"Схема leads_* готова ({self.path})")

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        """Добавить колонки, которых нет в существующей базе (идемпотентно)."""
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE_COMPANIES})")}
        for name, ddl in (
            ("country", "TEXT NOT NULL DEFAULT ''"),
            ("activity", "TEXT NOT NULL DEFAULT ''"),
            ("offers", "TEXT NOT NULL DEFAULT '[]'"),
            ("requests", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if name not in existing:
                conn.execute(f"ALTER TABLE {TABLE_COMPANIES} ADD COLUMN {name} {ddl}")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── запись ──

    def upsert_companies(self, companies: list[LeadCompany]) -> tuple[int, int]:
        """Сохранить компании по ключу дедупликации."""
        if not companies:
            return 0, 0

        self.migrate()
        conn = self._connect()
        inserted = updated = 0

        for company in companies:
            key = company_key(company)
            if not key:
                continue

            row = conn.execute(
                f"SELECT id FROM {TABLE_COMPANIES} WHERE dedup_key = ?", (key,)
            ).fetchone()

            payload = self._to_row(company, key)

            if row is None:
                columns = ", ".join(payload)
                placeholders = ", ".join("?" for _ in payload)
                cursor = conn.execute(
                    f"INSERT INTO {TABLE_COMPANIES} ({columns}) VALUES ({placeholders})",
                    tuple(payload.values()),
                )
                company_id = int(cursor.lastrowid or 0)
                inserted += 1
            else:
                company_id = int(row["id"])
                assignments = ", ".join(f"{name} = ?" for name in payload if name != "first_seen")
                values = [value for name, value in payload.items() if name != "first_seen"]
                conn.execute(
                    f"UPDATE {TABLE_COMPANIES} SET {assignments} WHERE id = ?",
                    (*values, company_id),
                )
                updated += 1

            self._upsert_emails(conn, company_id, company.emails)

        conn.commit()
        logger.info(f"Компании: вставлено {inserted}, обновлено {updated}")
        return inserted, updated

    @staticmethod
    def _to_row(company: LeadCompany, key: str) -> dict[str, Any]:
        return {
            "dedup_key": key,
            "company_name_en": company.company_name_en,
            "company_name_zh": company.company_name_zh,
            "province": company.province,
            "city": company.city,
            "country": company.country,
            "website": company.website,
            "domain": company.domain,
            "phones": json.dumps(company.phones, ensure_ascii=False),
            "wechat": company.wechat,
            "whatsapp": company.whatsapp,
            "matched_keywords": json.dumps(company.matched_keywords, ensure_ascii=False),
            "profile": company.profile,
            "industry_guess": company.industry_guess,
            "activity": company.activity,
            "offers": json.dumps(company.offers, ensure_ascii=False),
            "requests": json.dumps(company.requests, ensure_ascii=False),
            "source_url": company.source_url,
            "source_name": company.source_name,
            "enrich_status": company.enrich_status,
            "enrich_note": company.enrich_note,
            "first_seen": company.first_seen.isoformat(),
            "last_seen": company.last_seen.isoformat(),
        }

    @staticmethod
    def _upsert_emails(conn: sqlite3.Connection, company_id: int, emails: list[LeadEmail]) -> None:
        """Добавить новые адреса, у известных обновить last_seen."""
        for item in emails:
            conn.execute(
                f"""
                INSERT INTO {TABLE_EMAILS}
                    (company_id, email, kind, source_url, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, email) DO UPDATE SET
                    last_seen  = excluded.last_seen,
                    kind       = excluded.kind,
                    source_url = CASE
                        WHEN {TABLE_EMAILS}.source_url = '' THEN excluded.source_url
                        ELSE {TABLE_EMAILS}.source_url
                    END
                """,
                (
                    company_id,
                    item.email,
                    item.kind,
                    item.source_url,
                    item.first_seen.isoformat(),
                    item.last_seen.isoformat(),
                ),
            )

    def log_run(
        self,
        command: str,
        profile: str,
        found: int,
        inserted: int,
        updated: int,
        status: str,
        note: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.migrate()
        conn = self._connect()
        conn.execute(
            f"""
            INSERT INTO {TABLE_RUNS}
                (command, profile, found, inserted, updated, status, note, duration_ms, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (command, profile, found, inserted, updated, status, note[:500],
             duration_ms, utcnow().isoformat()),
        )
        conn.commit()

    # ── чтение ──

    def fetch_by_keys(self, keys: list[str]) -> dict[str, LeadCompany]:
        if not keys:
            return {}

        self.migrate()
        conn = self._connect()
        found: dict[str, LeadCompany] = {}

        # SQLite ограничивает число параметров — читаем пачками.
        for start in range(0, len(keys), 500):
            chunk = keys[start : start + 500]
            placeholders = ", ".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT * FROM {TABLE_COMPANIES} WHERE dedup_key IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            for row in rows:
                found[row["dedup_key"]] = self._from_row(conn, row)

        return found

    def iter_companies(
        self,
        profile: str = "",
        enrich_status: str = "",
        with_domain_only: bool = False,
        limit: int = 0,
    ) -> list[LeadCompany]:
        self.migrate()
        conn = self._connect()

        where: list[str] = []
        params: list[Any] = []
        if profile:
            where.append("profile = ?")
            params.append(profile)
        if enrich_status:
            where.append("enrich_status = ?")
            params.append(enrich_status)
        if with_domain_only:
            where.append("domain != ''")

        query = f"SELECT * FROM {TABLE_COMPANIES}"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id"
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, tuple(params)).fetchall()
        return [self._from_row(conn, row) for row in rows]

    def _from_row(self, conn: sqlite3.Connection, row: sqlite3.Row) -> LeadCompany:
        emails = [
            LeadEmail(
                email=e["email"],
                kind=e["kind"],
                source_url=e["source_url"],
                first_seen=_parse_dt(e["first_seen"]),
                last_seen=_parse_dt(e["last_seen"]),
            )
            for e in conn.execute(
                f"SELECT * FROM {TABLE_EMAILS} WHERE company_id = ? ORDER BY id",
                (row["id"],),
            ).fetchall()
        ]

        return LeadCompany(
            company_name_en=row["company_name_en"],
            company_name_zh=row["company_name_zh"],
            province=row["province"],
            city=row["city"],
            country=row["country"],
            website=row["website"],
            domain=row["domain"],
            emails=emails,
            phones=json.loads(row["phones"] or "[]"),
            wechat=row["wechat"],
            whatsapp=row["whatsapp"],
            matched_keywords=json.loads(row["matched_keywords"] or "[]"),
            profile=row["profile"],
            industry_guess=row["industry_guess"],
            activity=row["activity"],
            offers=json.loads(row["offers"] or "[]"),
            requests=json.loads(row["requests"] or "[]"),
            source_url=row["source_url"],
            source_name=row["source_name"],
            first_seen=_parse_dt(row["first_seen"]),
            last_seen=_parse_dt(row["last_seen"]),
            enrich_status=row["enrich_status"],
            enrich_note=row["enrich_note"],
        )

    def stats(self, profile: str = "") -> dict[str, Any]:
        self.migrate()
        conn = self._connect()

        where = " WHERE profile = ?" if profile else ""
        params: tuple = (profile,) if profile else ()

        total = conn.execute(
            f"SELECT count(*) AS n FROM {TABLE_COMPANIES}{where}", params
        ).fetchone()["n"]

        join = f"JOIN {TABLE_COMPANIES} c ON c.id = e.company_id"
        email_where = " WHERE c.profile = ?" if profile else ""
        role_where = (
            " WHERE c.profile = ? AND e.kind = 'role'" if profile else " WHERE e.kind = 'role'"
        )

        emails_total = conn.execute(
            f"SELECT count(*) AS n FROM {TABLE_EMAILS} e {join}{email_where}", params
        ).fetchone()["n"]
        emails_role = conn.execute(
            f"SELECT count(*) AS n FROM {TABLE_EMAILS} e {join}{role_where}", params
        ).fetchone()["n"]

        by_profile = {
            r["profile"] or "(без профиля)": r["n"]
            for r in conn.execute(
                f"SELECT profile, count(*) AS n FROM {TABLE_COMPANIES}{where} "
                f"GROUP BY profile ORDER BY n DESC",
                params,
            ).fetchall()
        }
        by_province = {
            r["province"] or "(не определена)": r["n"]
            for r in conn.execute(
                f"SELECT province, count(*) AS n FROM {TABLE_COMPANIES}{where} "
                f"GROUP BY province ORDER BY n DESC",
                params,
            ).fetchall()
        }
        by_status = {
            r["enrich_status"]: r["n"]
            for r in conn.execute(
                f"SELECT enrich_status, count(*) AS n FROM {TABLE_COMPANIES}{where} "
                f"GROUP BY enrich_status ORDER BY n DESC",
                params,
            ).fetchall()
        }
        with_emails = conn.execute(
            f"SELECT count(DISTINCT e.company_id) AS n FROM {TABLE_EMAILS} e {join}{email_where}",
            params,
        ).fetchone()["n"]

        return {
            "companies": total,
            "companies_with_emails": with_emails,
            "emails": emails_total,
            "emails_role": emails_role,
            "emails_personal": emails_total - emails_role,
            "by_profile": by_profile,
            "by_province": by_province,
            "by_enrich_status": by_status,
            "storage": f"sqlite:{self.path}",
        }


__all__ = ["SqliteLeadsRepository", "SCHEMA"]
