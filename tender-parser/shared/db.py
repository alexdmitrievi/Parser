"""Supabase клиент — все операции с БД."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

from supabase import create_client, Client

from shared.config import get_config
from shared.models import TenderCreate, SubscriptionCreate, SearchFilters

logger = logging.getLogger(__name__)

_db_client: Client | None = None
_db_url: str = ""


def get_db() -> Client:
    """Получить кешированный Supabase клиент (singleton)."""
    global _db_client, _db_url
    cfg = get_config()
    url = cfg["supabase_url"]
    key = cfg["supabase_key"]
    if _db_client is None or url != _db_url:
        _db_client = create_client(url, key)
        _db_url = url
    return _db_client


# ──────────────────────── Тендеры ────────────────────────


def insert_tenders(tenders: list[TenderCreate]) -> int:
    """Вставить тендеры с дедупликацией (upsert по source_platform + registry_number).
    Дедуплицирует внутри батча и отправляет частями по 200.
    Возвращает количество вставленных/обновлённых записей.
    """
    if not tenders:
        return 0

    db = get_db()
    # Дедупликация внутри батча по (source_platform, registry_number)
    seen: set[tuple[str, str]] = set()
    rows = []
    for t in tenders:
        reg = t.registry_number
        if not reg:
            fallback = hashlib.sha256(
                f"{t.source_platform}|{t.title}|{t.customer_name or ''}|{t.original_url or ''}".encode()
            ).hexdigest()[:24]
            reg = f"_gen_{fallback}"
            t.registry_number = reg
        key = (t.source_platform, reg)
        if key in seen:
            continue
        seen.add(key)
        # Поддержка sources из TenderCreate
        t.sources = list(dict.fromkeys((t.sources or []) + [t.source_platform]))
        data = t.model_dump(mode="json")
        if data.get("publish_date"):
            data["publish_date"] = str(data["publish_date"])
        if data.get("submission_deadline"):
            data["submission_deadline"] = str(data["submission_deadline"])
        if data.get("auction_date"):
            data["auction_date"] = str(data["auction_date"])
        rows.append(data)

    total = 0
    errors = 0
    batch_size = 200
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            result = (
                db.table("tenders")
                .upsert(batch, on_conflict="source_platform,registry_number")
                .execute()
            )
            count = len(result.data) if result.data else 0
            total += count
        except Exception as e:
            errors += 1
            logger.error(f"Error inserting batch {i//batch_size}: {e}")

    logger.info(f"Upserted {total} tenders (from {len(rows)} unique, {errors} batch errors)")
    if errors > 0 and total == 0:
        raise RuntimeError(f"All {errors} insert batches failed — check DB connection")
    return total


def _stem_russian(word: str) -> str:
    """Простейшая стемминг-функция: обрезает типичные русские окончания."""
    word = word.lower().strip()
    if len(word) <= 3:
        return word
    # Обрезаем типичные окончания (от длинных к коротким)
    for suffix in [
        "ьями", "ями", "иях", "ьях", "ами", "ями",
        "ого", "его", "ому", "ему", "ыми", "ими",
        "ьев", "ьёв", "ьям", "ией", "иям",
        "ов", "ев", "ёв", "ей", "ий", "ой", "ый", "ая", "яя",
        "ые", "ие", "ых", "их", "ям", "ях", "ам", "ах",
        "ом", "ем", "ём", "ть", "ся",
        "а", "я", "о", "е", "ё", "у", "ю", "ы", "и",
    ]:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _sanitize_postgrest(value: str) -> str:
    """Удалить спецсимволы PostgREST из пользовательского ввода."""
    return re.sub(r"[,.()\[\]{}]", " ", value).strip()


def _apply_common_filters(query: Any, filters: SearchFilters) -> Any:
    """Apply common filters to query (used in search and count). Uses ilike for text search."""
    if filters.query:
        q = _sanitize_postgrest(filters.query.strip())
        if q:
            words = [w for w in q.split() if len(w) >= 2][:5]
            if words:
                safe_words = [re.sub(r"[*_]", "", w) for w in words]
                safe_words = [w for w in safe_words if len(w) >= 2]
                if safe_words:
                    or_filters = []
                    for w in safe_words:
                        or_filters.append(f"title.ilike.*{w}*,description.ilike.*{w}*")
                    query = query.or_(','.join(or_filters))
    if filters.region:
        r = _sanitize_postgrest(filters.region)
        if r:
            query = query.eq("customer_region", r) if len(r) >= 3 else query
    # ... rest of filters unchanged
    if filters.min_nmck is not None:
        query = query.gte("nmck", filters.min_nmck)
    if filters.max_nmck is not None:
        query = query.lte("nmck", filters.max_nmck)
    if filters.okpd2:
        query = query.contains("okpd2_codes", [filters.okpd2])
    if filters.niche:
        query = query.contains("niche_tags", [filters.niche])
    if filters.status:
        query = query.eq("status", filters.status)
    if filters.law_type:
        query = query.eq("law_type", filters.law_type)
    if filters.purchase_method:
        query = query.eq("purchase_method", filters.purchase_method)
    if filters.source_platform:
        query = query.eq("source_platform", filters.source_platform)
    if filters.date_from:
        query = query.gte("publish_date", filters.date_from)
    if filters.date_to:
        query = query.lte("publish_date", filters.date_to + "T23:59:59")
    return query


def search_tenders(filters: SearchFilters) -> list[dict]:
    """Поиск тендеров с фильтрами и пагинацией."""
    db = get_db()
    query = db.table("tenders").select("*")
    query = _apply_common_filters(query, filters)

    sort_col = {
        "deadline": "submission_deadline",
        "nmck": "nmck",
        "publish_date": "publish_date",
    }.get(filters.sort_by, "created_at")

    offset = (filters.page - 1) * filters.per_page
    query = (
        query
        .order(sort_col, desc=True)
        .range(offset, offset + filters.per_page - 1)
    )

    try:
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"search_tenders failed: {e}", extra={"filters": str(filters.dict()) if hasattr(filters, 'dict') else str(filters)})
        raise  # Let API layer decide how to respond


def count_tenders(filters: SearchFilters) -> int:
    """Подсчёт тендеров по фильтрам (те же условия, что и search_tenders)."""
    db = get_db()
    query = db.table("tenders").select("id", count="exact")
    query = _apply_common_filters(query, filters)

    try:
        result = query.execute()
        return result.count or 0
    except Exception as e:
        logger.error(f"count_tenders failed: {e}")
        raise


def suggest_regions(q: str, limit: int = 10) -> list[str]:
    """Поиск регионов по подстроке (distinct customer_region)."""
    db = get_db()
    try:
        result = (
            db.table("tenders")
            .select("customer_region")
            .ilike("customer_region", f"%{q}%")
            .neq("customer_region", "")
            .limit(200)
            .execute()
        )
        seen: set[str] = set()
        out: list[str] = []
        for r in result.data or []:
            val = (r.get("customer_region") or "").strip()
            if val and val not in seen:
                seen.add(val)
                out.append(val)
                if len(out) >= limit:
                    break
        return out
    except Exception as e:
        logger.error(f"suggest_regions: {e}")
        return []


def suggest_customers(q: str, limit: int = 10) -> list[str]:
    """Поиск заказчиков по подстроке (distinct customer_name)."""
    db = get_db()
    try:
        result = (
            db.table("tenders")
            .select("customer_name")
            .ilike("customer_name", f"%{q}%")
            .neq("customer_name", "")
            .limit(200)
            .execute()
        )
        seen: set[str] = set()
        out: list[str] = []
        for r in result.data or []:
            val = (r.get("customer_name") or "").strip()
            if val and val not in seen:
                seen.add(val)
                out.append(val)
                if len(out) >= limit:
                    break
        return out
    except Exception as e:
        logger.error(f"suggest_customers: {e}")
        return []


def get_new_tenders_since(since_minutes: int = 60) -> list[dict]:
    """Получить тендеры, добавленные за последние N минут."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()

    try:
        result = (
            db.table("tenders")
            .select("*")
            .gte("created_at", cutoff)
            .eq("status", "active")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching new tenders: {e}")
        return []


# ──────────────────────── Подписки ────────────────────────


def get_subscriptions(telegram_user_id: Optional[int] = None) -> list[dict]:
    """Получить подписки. Если user_id указан — только его."""
    db = get_db()
    query = db.table("subscriptions").select("*").eq("is_active", True)
    if telegram_user_id:
        query = query.eq("telegram_user_id", telegram_user_id)

    try:
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching subscriptions: {e}")
        return []


def add_subscription(sub: SubscriptionCreate) -> Optional[dict]:
    """Создать подписку."""
    db = get_db()
    try:
        result = (
            db.table("subscriptions")
            .insert(sub.model_dump(mode="json"))
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        return None


def delete_subscription(sub_id: str, telegram_user_id: int) -> bool:
    """Удалить подписку пользователя."""
    db = get_db()
    try:
        db.table("subscriptions").delete().eq("id", sub_id).eq(
            "telegram_user_id", telegram_user_id
        ).execute()
        return True
    except Exception:
        return False


def count_user_subscriptions(telegram_user_id: int) -> int:
    """Подсчитать количество подписок пользователя."""
    db = get_db()
    try:
        result = (
            db.table("subscriptions")
            .select("id", count="exact")
            .eq("telegram_user_id", telegram_user_id)
            .eq("is_active", True)
            .execute()
        )
        return result.count or 0
    except Exception:
        return 0


# ──────────────────────── Уведомления ────────────────────────


def check_notification_sent(subscription_id: str, tender_id: str) -> bool:
    """Проверить, было ли уже отправлено уведомление."""
    db = get_db()
    try:
        result = (
            db.table("notifications_log")
            .select("id")
            .eq("subscription_id", subscription_id)
            .eq("tender_id", tender_id)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


def log_notification(subscription_id: str, tender_id: str) -> None:
    """Записать факт отправки уведомления."""
    db = get_db()
    try:
        db.table("notifications_log").insert({
            "subscription_id": subscription_id,
            "tender_id": tender_id,
        }).execute()
    except Exception as e:
        logger.error(f"Error logging notification: {e}")


# ──────────────────────── Пользователи бота ────────────────────────


def register_user(telegram_user_id: int, username: str = "", first_name: str = "") -> None:
    """Зарегистрировать или обновить пользователя бота."""
    db = get_db()
    try:
        db.table("bot_users").upsert({
            "telegram_user_id": telegram_user_id,
            "username": username or "",
            "first_name": first_name or "",
        }, on_conflict="telegram_user_id").execute()
    except Exception as e:
        logger.error(f"Error registering user: {e}")


# ──────────────────────── Dict-строки (scrapers/scripts/run_parser) ────────────────────────


def _serialize_row_for_db(row: dict[str, Any]) -> dict[str, Any]:
    """Привести dict парсера к колонкам таблицы tenders."""
    out = dict(row)
    if "external_url" in out:
        out["original_url"] = out.pop("external_url") or out.get("original_url")
    if "raw_payload" in out:
        out["raw_data"] = out.pop("raw_payload")
    for key in ("publish_date", "submission_deadline", "auction_date"):
        val = out.get(key)
        if isinstance(val, datetime):
            out[key] = val.isoformat()
    return out


def fetch_tender_by_registry(registry_number: str) -> dict[str, Any] | None:
    """Одна запись по номеру закупки (для merge при дедупликации)."""
    if not (registry_number or "").strip():
        return None
    db = get_db()
    try:
        result = (
            db.table("tenders")
            .select("*")
            .eq("registry_number", registry_number.strip())
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.error(f"fetch_tender_by_registry: {e}")
        return None


def upsert_tender(row: dict[str, Any]) -> None:
    """Upsert dict-строки (альт. парсер); конфликт по source_platform + registry_number."""
    db = get_db()
    payload = _serialize_row_for_db(row)
    sp = payload.get("source_platform")
    reg = payload.get("registry_number")
    if not sp or not reg:
        logger.warning("upsert_tender: missing source_platform or registry_number")
        return
    try:
        db.table("tenders").upsert(
            payload, on_conflict="source_platform,registry_number"
        ).execute()
    except Exception as e:
        logger.error(f"upsert_tender: {e}")


# ──────────────────────── Состояние бота (bot_state) ────────────────────────


def get_user_state(telegram_user_id: int) -> dict[str, Any]:
    """Получить состояние диалога бота (wizard step, фильтры и т.д.)."""
    db = get_db()
    try:
        result = (
            db.table("bot_state")
            .select("data")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return dict(rows[0]["data"]) if rows and rows[0].get("data") else {}
    except Exception as e:
        logger.error(f"get_user_state: {e}")
        return {}


def set_user_state(telegram_user_id: int, state: dict[str, Any]) -> None:
    """Сохранить состояние диалога бота (upsert в bot_state)."""
    db = get_db()
    try:
        db.table("bot_state").upsert(
            {
                "telegram_user_id": telegram_user_id,
                "state": "",
                "data": state,
            },
            on_conflict="telegram_user_id",
        ).execute()
    except Exception as e:
        logger.error(f"set_user_state: {e}")


def clear_user_state(telegram_user_id: int) -> None:
    """Очистить состояние диалога бота."""
    set_user_state(telegram_user_id, {})


# ──────────────────────── Агрегация (RPC) ────────────────────────


def get_stats_via_rpc() -> dict:
    """Статистика через DB-агрегацию (не грузит строки в память)."""
    db = get_db()
    try:
        result = db.rpc("get_tender_stats").execute()
        return result.data if result.data else {}
    except Exception as e:
        logger.warning(f"get_tender_stats RPC failed, falling back: {e}")
        return _get_stats_fallback()


def get_meta_via_rpc() -> dict:
    """Meta enrichment через DB-агрегацию."""
    db = get_db()
    try:
        result = db.rpc("get_tender_meta").execute()
        return result.data if result.data else {}
    except Exception as e:
        logger.warning(f"get_tender_meta RPC failed, falling back: {e}")
        return _get_meta_fallback()


def _get_stats_fallback() -> dict:
    """Fallback: in-Python aggregation (для старой БД без RPC)."""
    db = get_db()
    total_res = db.table("tenders").select("id", count="exact").execute()
    total = total_res.count or 0
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_res = db.table("tenders").select("id", count="exact").gte("created_at", week_ago).execute()
    recent = recent_res.count or 0
    res = db.table("tenders").select("niche_tags, customer_region, source_platform").limit(5000).execute()
    by_niche: dict[str, int] = {}
    by_region: dict[str, int] = {}
    platforms: set[str] = set()
    for r in res.data or []:
        for t in r.get("niche_tags") or []:
            by_niche[t] = by_niche.get(t, 0) + 1
        reg = r.get("customer_region") or "unknown"
        by_region[reg] = by_region.get(reg, 0) + 1
        plat = r.get("source_platform")
        if plat:
            platforms.add(plat)
    return {
        "total": total, "platforms": len(platforms),
        "by_niche": by_niche, "by_region": by_region,
        "created_last_7_days": recent,
    }


def _get_meta_fallback() -> dict:
    """Fallback для meta."""
    db = get_db()
    res = db.table("tenders").select("niche_tags,source_platform,purchase_method").limit(5000).execute()
    rows = res.data or []
    niche_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    for r in rows:
        for t in r.get("niche_tags") or []:
            niche_counts[t] = niche_counts.get(t, 0) + 1
        p = r.get("source_platform", "")
        if p:
            platform_counts[p] = platform_counts.get(p, 0) + 1
        m = r.get("purchase_method", "")
        if m:
            method_counts[m] = method_counts.get(m, 0) + 1
    return {
        "niches": [{"name": k, "count": v} for k, v in sorted(niche_counts.items())],
        "platforms": [{"id": k, "name": k, "count": v} for k, v in sorted(platform_counts.items())],
        "methods": [{"id": k, "name": k, "count": v} for k, v in sorted(method_counts.items())],
    }


# ──────────────────────── Funding ────────────────────────


def get_funding_programs(
    q: str | None = None,
    region: str | None = None,
    program_type: str | None = None,
    industry: str | None = None,
    amount_max: float | None = None,
    source_platform: str | None = None,
    status: str = "active",
    page: int = 1,
    page_size: int = 12,
) -> tuple[list[dict], int]:
    """Поиск программ финансирования с фильтрами. Возвращает (rows, total)."""
    db = get_db()
    qb = db.table("funding_programs").select("*", count="exact")
    if status and status != "all":
        qb = qb.eq("status", status)
    if q:
        qb = qb.ilike("program_name", f"%{_sanitize_postgrest(q)}%")
    if region:
        qb = qb.contains("regions", [region])
    if program_type:
        qb = qb.eq("program_type", program_type)
    if amount_max is not None:
        qb = qb.lte("amount_min", amount_max)
    if source_platform:
        qb = qb.eq("source_platform", source_platform)
    start = (page - 1) * page_size
    try:
        res = qb.order("created_at", desc=True).range(start, start + page_size - 1).execute()
        total = getattr(res, "count", None) or 0
        return res.data or [], total
    except Exception as e:
        logger.error(f"get_funding_programs: {e}")
        return [], 0


def get_funding_detail(program_id: str) -> dict | None:
    """Одна программа финансирования по ID."""
    db = get_db()
    try:
        res = db.table("funding_programs").select("*").eq("id", program_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.error(f"get_funding_detail: {e}")
        return None


def get_funding_meta_via_rpc() -> dict:
    """Funding meta через RPC."""
    db = get_db()
    try:
        result = db.rpc("get_funding_meta").execute()
        return result.data if result.data else {}
    except Exception as e:
        logger.warning(f"get_funding_meta RPC failed: {e}")
        db = get_db()
        total = db.table("funding_programs").select("id", count="exact").eq("status", "active").execute()
        return {"total_active": total.count or 0, "by_type": [], "by_platform": []}


def get_niches() -> list[dict]:
    """Список ниш с количеством тендеров."""
    db = get_db()
    try:
        res = db.table("tenders").select("niche_tags").limit(5000).execute()
    except Exception as e:
        logger.error(f"niches: {e}")
        return []
    rows = res.data or []
    counts: dict[str, int] = {}
    for r in rows:
        for t in r.get("niche_tags") or []:
            counts[t] = counts.get(t, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(counts.items())]


# ──────────────────────── Scrape Log ────────────────────────


def log_scrape_start(scraper_name: str, source_group: str) -> str | None:
    """Записать начало парсинга, вернуть ID записи."""
    db = get_db()
    try:
        result = db.table("scrape_log").insert({
            "scraper_name": scraper_name,
            "source_group": source_group,
            "status": "running",
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        logger.warning(f"log_scrape_start: {e}")
        return None


def log_scrape_finish(
    log_id: str | None, status: str,
    tenders_found: int = 0, tenders_inserted: int = 0,
    error_message: str = "", duration_ms: int = 0,
) -> None:
    """Обновить запись парсинга после завершения."""
    if not log_id:
        return
    db = get_db()
    try:
        payload: dict[str, Any] = {"status": status, "completed_at": datetime.now(timezone.utc).isoformat()}
        if tenders_found:
            payload["tenders_found"] = tenders_found
        if tenders_inserted:
            payload["tenders_inserted"] = tenders_inserted
        if error_message:
            payload["error_message"] = error_message[:500]
        if duration_ms:
            payload["duration_ms"] = duration_ms
        db.table("scrape_log").update(payload).eq("id", log_id).execute()
    except Exception as e:
        logger.warning(f"log_scrape_finish: {e}")


def get_scrape_health() -> list[dict]:
    """Последние результаты всех скрейперов (для health/full)."""
    db = get_db()
    try:
        res = db.table("scrape_log").select("*").order("started_at", desc=True).limit(50).execute()
        return res.data or []
    except Exception:
        return []


# ──────────────────────── Rate Limiter (DB-based) ────────────────────────


def check_rate_limit(ip: str, endpoint: str, max_requests: int = 30, window_seconds: int = 60) -> bool:
    """Проверить лимит запросов для IP. True = разрешено."""
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=window_seconds)).isoformat()
    try:
        existing = db.table("rate_limits").select("count,window_start").eq("ip", ip).eq("endpoint", endpoint).execute()
        row = existing.data[0] if existing.data else None
        if row:
            window_start = row.get("window_start")
            if window_start:
                ws = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
                if (now - ws).total_seconds() < window_seconds:
                    if row["count"] >= max_requests:
                        return False
                    db.table("rate_limits").update({"count": row["count"] + 1}).eq("ip", ip).eq("endpoint", endpoint).execute()
                    return True
            db.table("rate_limits").update({"window_start": now.isoformat(), "count": 1}).eq("ip", ip).eq("endpoint", endpoint).execute()
        else:
            db.table("rate_limits").insert({"ip": ip, "endpoint": endpoint, "window_start": now.isoformat(), "count": 1}).execute()
        return True
    except Exception as e:
        logger.warning(f"rate_limit check failed: {e}")
        return True


def cleanup_old_rate_limits() -> None:
    """Удалить устаревшие записи rate_limits (вызывать из cron)."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    try:
        db.table("rate_limits").delete().lt("window_start", cutoff).execute()
    except Exception as e:
        logger.warning(f"cleanup_old_rate_limits: {e}")


