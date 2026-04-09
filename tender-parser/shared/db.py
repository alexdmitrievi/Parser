"""Supabase клиент — все операции с БД."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional

from supabase import create_client, Client

from shared.config import get_config, supabase_url, supabase_key
from shared.models import TenderCreate, SubscriptionCreate, SearchFilters

logger = logging.getLogger(__name__)

# ─── Singleton клиент (создаётся один раз, thread-safe) ──────────────────────
_db_client: Optional[Client] = None
_db_lock = threading.Lock()


def get_db() -> Client:
    """Получить Supabase клиент (singleton).

    Raises:
        RuntimeError: если SUPABASE_URL / SUPABASE_KEY не заданы.
    """
    global _db_client
    if _db_client is not None:
        return _db_client
    with _db_lock:
        if _db_client is None:
            url = supabase_url()
            key = supabase_key()
            if not url or not key:
                raise RuntimeError(
                    "Supabase не настроен: задайте SUPABASE_URL и SUPABASE_KEY "
                    "в secrets GitHub Actions."
                )
            _db_client = create_client(url, key)
            logger.info("Supabase client initialized")
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
        key = (t.source_platform, t.registry_number or "")
        if key in seen:
            continue
        seen.add(key)
        data = t.model_dump(mode="json")
        if data.get("publish_date"):
            data["publish_date"] = str(data["publish_date"])
        if data.get("submission_deadline"):
            data["submission_deadline"] = str(data["submission_deadline"])
        if data.get("auction_date"):
            data["auction_date"] = str(data["auction_date"])
        rows.append(data)

    total = 0
    batch_size = 200
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_idx = i // batch_size
        # Retry с экспоненциальным backoff для transient-ошибок (504, connection reset)
        for attempt in range(3):
            try:
                result = (
                    db.table("tenders")
                    .upsert(batch, on_conflict="source_platform,registry_number")
                    .execute()
                )
                count = len(result.data) if result.data else 0
                total += count
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        f"Batch {batch_idx} insert attempt {attempt+1} failed: {e} "
                        f"— retry in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"Batch {batch_idx} failed after 3 attempts: {e}")

    logger.info(f"Upserted {total} tenders (from {len(rows)} unique)")
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


def _apply_common_filters(query: Any, filters: SearchFilters) -> Any:
    """Применить общие фильтры к запросу (используется в search и count)."""
    if filters.query:
        # Ищем каждое слово запроса (обрезанное до корня) в title, description, customer_name
        words = filters.query.strip().split()
        for word in words:
            stem = _stem_russian(word)
            if len(stem) < 2:
                stem = word.lower()
            query = query.or_(
                f"title.ilike.%{stem}%,description.ilike.%{stem}%,customer_name.ilike.%{stem}%"
            )
    if filters.region:
        # Ищем регион в customer_region, customer_name, title и description
        r = filters.region
        query = query.or_(f"customer_region.ilike.%{r}%,customer_name.ilike.%{r}%,title.ilike.%{r}%,description.ilike.%{r}%")
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
        logger.error(f"Error searching tenders: {e}")
        return []


def count_tenders(filters: SearchFilters) -> int:
    """Подсчёт тендеров по фильтрам (те же условия, что и search_tenders)."""
    db = get_db()
    query = db.table("tenders").select("id", count="exact")
    query = _apply_common_filters(query, filters)

    try:
        result = query.execute()
        return result.count or 0
    except Exception:
        return 0


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
    from datetime import datetime, timedelta, timezone
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
