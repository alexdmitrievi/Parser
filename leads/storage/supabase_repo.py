"""Supabase-хранилище лидов (``LEADS_STORAGE=supabase``).

Работает с таблицами ``leads_companies``, ``leads_emails`` и ``leads_runs``,
которые создаёт ``scripts/migration_leads.sql``. Существующих таблиц проекта
(``tenders``, ``funding_programs`` и прочих) не касается.

Клиент Supabase берётся через ``shared.config`` — те же URL и ключ, что и у
остального проекта.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from engine.observability.logger import get_logger
from leads.dedup import company_key
from leads.models import LeadCompany, LeadEmail, utcnow
from leads.storage.base import TABLE_COMPANIES, TABLE_EMAILS, TABLE_RUNS, LeadsRepository

logger = get_logger("leads.storage.supabase")

# Supabase/PostgREST ограничивает размер запроса — пишем пачками.
BATCH_SIZE = 200


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return utcnow()


class SupabaseLeadsRepository(LeadsRepository):
    """Хранилище лидов поверх Supabase."""

    def __init__(self, client: Any = None):
        self._client = client

    def _db(self) -> Any:
        if self._client is None:
            from supabase import create_client

            from shared.config import supabase_key, supabase_url

            url, key = supabase_url(), supabase_key()
            if not url or not key:
                raise RuntimeError(
                    "LEADS_STORAGE=supabase, но SUPABASE_URL/SUPABASE_KEY не заданы. "
                    "Задайте ключи или переключитесь на LEADS_STORAGE=sqlite."
                )
            self._client = create_client(url, key)
        return self._client

    def migrate(self) -> None:
        """Проверить, что схема применена.

        Supabase не даёт выполнять DDL через клиентский API, поэтому миграция
        применяется руками: ``scripts/migration_leads.sql`` в SQL Editor.
        Здесь мы только убеждаемся, что таблицы существуют, и говорим что
        делать, если нет.
        """
        try:
            self._db().table(TABLE_COMPANIES).select("id").limit(1).execute()
        except Exception as e:
            raise RuntimeError(
                f"Таблица {TABLE_COMPANIES} недоступна ({e}). "
                "Примените scripts/migration_leads.sql в Supabase SQL Editor. "
                "Миграция идемпотентна — повторный запуск безопасен."
            ) from e

    # ── запись ──

    def upsert_companies(self, companies: list[LeadCompany]) -> tuple[int, int]:
        if not companies:
            return 0, 0

        db = self._db()
        keys = [company_key(c) for c in companies]
        existing = self.fetch_by_keys([k for k in keys if k])

        rows: list[dict[str, Any]] = []
        inserted = updated = 0
        for company in companies:
            key = company_key(company)
            if not key:
                continue
            rows.append(self._to_row(company, key))
            if key in existing:
                updated += 1
            else:
                inserted += 1

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            try:
                db.table(TABLE_COMPANIES).upsert(batch, on_conflict="dedup_key").execute()
            except Exception as e:
                logger.error(f"upsert компаний (пачка {start // BATCH_SIZE}) не удался: {e}")

        self._upsert_emails(companies)
        logger.info(f"Компании: вставлено {inserted}, обновлено {updated}")
        return inserted, updated

    def _upsert_emails(self, companies: list[LeadCompany]) -> None:
        """Записать почты, привязав их к id компаний по dedup_key."""
        db = self._db()
        keys = [company_key(c) for c in companies if company_key(c)]
        id_by_key = self._ids_for_keys(keys)

        rows: list[dict[str, Any]] = []
        for company in companies:
            company_id = id_by_key.get(company_key(company))
            if company_id is None:
                continue
            for item in company.emails:
                rows.append({
                    "company_id": company_id,
                    "email": item.email,
                    "kind": item.kind,
                    "source_url": item.source_url,
                    "first_seen": item.first_seen.isoformat(),
                    "last_seen": item.last_seen.isoformat(),
                })

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            try:
                db.table(TABLE_EMAILS).upsert(batch, on_conflict="company_id,email").execute()
            except Exception as e:
                logger.error(f"upsert почт (пачка {start // BATCH_SIZE}) не удался: {e}")

    def _ids_for_keys(self, keys: list[str]) -> dict[str, int]:
        if not keys:
            return {}
        db = self._db()
        mapping: dict[str, int] = {}
        for start in range(0, len(keys), BATCH_SIZE):
            chunk = keys[start : start + BATCH_SIZE]
            try:
                result = (
                    db.table(TABLE_COMPANIES)
                    .select("id,dedup_key")
                    .in_("dedup_key", chunk)
                    .execute()
                )
                for row in result.data or []:
                    mapping[row["dedup_key"]] = row["id"]
            except Exception as e:
                logger.error(f"Не удалось получить id компаний: {e}")
        return mapping

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
            "phones": list(company.phones),
            "wechat": company.wechat,
            "whatsapp": company.whatsapp,
            "matched_keywords": list(company.matched_keywords),
            "profile": company.profile,
            "industry_guess": company.industry_guess,
            "activity": company.activity,
            "offers": list(company.offers),
            "requests": list(company.requests),
            "source_url": company.source_url,
            "source_name": company.source_name,
            "enrich_status": company.enrich_status,
            "enrich_note": company.enrich_note,
            "first_seen": company.first_seen.isoformat(),
            "last_seen": company.last_seen.isoformat(),
        }

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
        try:
            self._db().table(TABLE_RUNS).insert({
                "command": command,
                "profile": profile,
                "found": found,
                "inserted": inserted,
                "updated": updated,
                "status": status,
                "note": note[:500],
                "duration_ms": duration_ms,
                "started_at": utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.warning(f"log_run не удался: {e}")

    # ── чтение ──

    def fetch_by_keys(self, keys: list[str]) -> dict[str, LeadCompany]:
        if not keys:
            return {}

        db = self._db()
        found: dict[str, LeadCompany] = {}

        for start in range(0, len(keys), BATCH_SIZE):
            chunk = keys[start : start + BATCH_SIZE]
            try:
                result = (
                    db.table(TABLE_COMPANIES).select("*").in_("dedup_key", chunk).execute()
                )
            except Exception as e:
                logger.error(f"Чтение компаний не удалось: {e}")
                continue

            rows = result.data or []
            emails = self._emails_for([row["id"] for row in rows])
            for row in rows:
                found[row["dedup_key"]] = self._from_row(row, emails.get(row["id"], []))

        return found

    def _emails_for(self, company_ids: list[int]) -> dict[int, list[LeadEmail]]:
        if not company_ids:
            return {}
        grouped: dict[int, list[LeadEmail]] = {}
        try:
            result = (
                self._db().table(TABLE_EMAILS).select("*").in_("company_id", company_ids).execute()
            )
            for row in result.data or []:
                grouped.setdefault(row["company_id"], []).append(
                    LeadEmail(
                        email=row["email"],
                        kind=row.get("kind", "role"),
                        source_url=row.get("source_url", ""),
                        first_seen=_parse_dt(row.get("first_seen")),
                        last_seen=_parse_dt(row.get("last_seen")),
                    )
                )
        except Exception as e:
            logger.error(f"Чтение почт не удалось: {e}")
        return grouped

    def iter_companies(
        self,
        profile: str = "",
        enrich_status: str = "",
        with_domain_only: bool = False,
        limit: int = 0,
    ) -> list[LeadCompany]:
        db = self._db()
        query = db.table(TABLE_COMPANIES).select("*")
        if profile:
            query = query.eq("profile", profile)
        if enrich_status:
            query = query.eq("enrich_status", enrich_status)
        if with_domain_only:
            query = query.neq("domain", "")
        if limit > 0:
            query = query.limit(limit)

        try:
            rows = query.execute().data or []
        except Exception as e:
            logger.error(f"Выборка компаний не удалась: {e}")
            return []

        emails = self._emails_for([row["id"] for row in rows])
        return [self._from_row(row, emails.get(row["id"], [])) for row in rows]

    @staticmethod
    def _from_row(row: dict[str, Any], emails: list[LeadEmail]) -> LeadCompany:
        return LeadCompany(
            company_name_en=row.get("company_name_en", ""),
            company_name_zh=row.get("company_name_zh", ""),
            province=row.get("province", ""),
            city=row.get("city", ""),
            country=row.get("country", ""),
            website=row.get("website", ""),
            domain=row.get("domain", ""),
            emails=emails,
            phones=list(row.get("phones") or []),
            wechat=row.get("wechat", ""),
            whatsapp=row.get("whatsapp", ""),
            matched_keywords=list(row.get("matched_keywords") or []),
            profile=row.get("profile", ""),
            industry_guess=row.get("industry_guess", ""),
            activity=row.get("activity", ""),
            offers=list(row.get("offers") or []),
            requests=list(row.get("requests") or []),
            source_url=row.get("source_url", ""),
            source_name=row.get("source_name", ""),
            first_seen=_parse_dt(row.get("first_seen")),
            last_seen=_parse_dt(row.get("last_seen")),
            enrich_status=row.get("enrich_status", "pending"),
            enrich_note=row.get("enrich_note", ""),
        )

    def stats(self, profile: str = "") -> dict[str, Any]:
        """Сводка по лидам.

        Агрегация делается в Python: объёмы домена leads (тысячи строк, не
        сотни тысяч) этого не оправдывают усложнения RPC-функциями.
        """
        companies = self.iter_companies(profile=profile)

        by_profile: dict[str, int] = {}
        by_province: dict[str, int] = {}
        by_status: dict[str, int] = {}
        emails_total = emails_role = with_emails = 0

        for company in companies:
            by_profile[company.profile or "(без профиля)"] = (
                by_profile.get(company.profile or "(без профиля)", 0) + 1
            )
            province = company.province or "(не определена)"
            by_province[province] = by_province.get(province, 0) + 1
            by_status[company.enrich_status] = by_status.get(company.enrich_status, 0) + 1

            if company.emails:
                with_emails += 1
            emails_total += len(company.emails)
            emails_role += len(company.role_emails)

        return {
            "companies": len(companies),
            "companies_with_emails": with_emails,
            "emails": emails_total,
            "emails_role": emails_role,
            "emails_personal": emails_total - emails_role,
            "by_profile": dict(sorted(by_profile.items(), key=lambda kv: -kv[1])),
            "by_province": dict(sorted(by_province.items(), key=lambda kv: -kv[1])),
            "by_enrich_status": dict(sorted(by_status.items(), key=lambda kv: -kv[1])),
            "storage": "supabase",
        }


__all__ = ["SupabaseLeadsRepository"]
