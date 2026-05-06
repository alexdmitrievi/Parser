"""
API route handlers — imported by api/tenders.py.
Contains all business logic, separated to keep Vercel handler minimal.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from urllib.parse import parse_qs

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

CORS_ORIGINS = "http://localhost:3000,http://localhost:8000,https://tender-pro.vercel.app,https://tender-parser.vercel.app"

PROGRAM_TYPE_LABELS = {
    "grant": "Грант", "loan": "Кредит", "microloan": "Микрозайм",
    "subsidy": "Субсидия", "guarantee": "Поручительство",
    "compensation": "Компенсация", "leasing": "Лизинг",
}

DESCRIPTIVE_PLATFORM_NAMES = {
    "eis": "ЕИС", "roseltorg": "Росэлторг", "sberbank_ast": "Сбербанк-АСТ",
    "rts_tender": "РТС-тендер", "tektorg": "ТЭК-Торг", "b2b_center": "B2B-Center",
    "tenderguru": "TenderGuru", "fabrikant": "Fabrikant", "tenderpro": "TenderPro",
    "etpgpb": "ЭТП ГПБ", "etp_ets": "ЭТП ЕТС", "rostender": "Ростендер",
    "corpmsp": "Корпорация МСП", "mybusiness": "Мой Бизнес",
    "frprf": "ФРП РФ", "mspbank": "МСП Банк",
}

RUSSIAN_REGIONS = [
    "Алтайский край", "Амурская область", "Архангельская область",
    "Астраханская область", "Белгородская область", "Брянская область",
    "Владимирская область", "Волгоградская область", "Вологодская область",
    "Воронежская область", "Забайкальский край", "Ивановская область",
    "Иркутская область", "Кабардино-Балкария", "Калининградская область",
    "Калужская область", "Камчатский край", "Кемеровская область",
    "Кировская область", "Костромская область", "Краснодарский край",
    "Красноярский край", "Курганская область", "Курская область",
    "Ленинградская область", "Липецкая область", "Москва",
    "Московская область", "Мурманская область", "Нижегородская область",
    "Новгородская область", "Новосибирская область", "Омская область",
    "Оренбургская область", "Орловская область", "Пензенская область",
    "Пермский край", "Приморский край", "Псковская область",
    "Республика Адыгея", "Республика Башкортостан", "Республика Бурятия",
    "Республика Дагестан", "Республика Ингушетия", "Республика Калмыкия",
    "Республика Карелия", "Республика Коми", "Республика Крым",
    "Республика Марий Эл", "Республика Мордовия", "Республика Саха (Якутия)",
    "Республика Северная Осетия", "Республика Татарстан",
    "Республика Тыва", "Республика Хакасия", "Ростовская область",
    "Рязанская область", "Самарская область", "Санкт-Петербург",
    "Саратовская область", "Сахалинская область", "Свердловская область",
    "Севастополь", "Смоленская область", "Ставропольский край",
    "Тамбовская область", "Тверская область", "Томская область",
    "Тульская область", "Тюменская область", "Удмуртская Республика",
    "Ульяновская область", "Хабаровский край", "Ханты-Мансийский АО",
    "Челябинская область", "Чеченская Республика", "Чувашская Республика",
    "Чукотский АО", "Ямало-Ненецкий АО", "Ярославская область",
]

PLATFORMS = [
    {"id": "eis", "name": "ЕИС"}, {"id": "roseltorg", "name": "Росэлторг"},
    {"id": "sberbank_ast", "name": "Сбербанк-АСТ"}, {"id": "rts_tender", "name": "РТС-тендер"},
    {"id": "tektorg", "name": "ТЭК-Торг"}, {"id": "b2b_center", "name": "B2B-Center"},
    {"id": "tenderguru", "name": "TenderGuru"}, {"id": "fabrikant", "name": "Fabrikant"},
    {"id": "tenderpro", "name": "TenderPro"}, {"id": "etpgpb", "name": "ЭТП ГПБ"},
    {"id": "etp_ets", "name": "ЭТП ЕТС"}, {"id": "rostender", "name": "Ростендер"},
]

PURCHASE_METHODS = ["Аукцион", "Конкурс", "Запрос котировок", "Запрос предложений", "Единственный поставщик", "Открытый аукцион"]

_db = None
_cache = {}
_CACHE_TTL = 300


def _json(h, status, data, cache_max_age=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    if cache_max_age:
        h.send_header("Cache-Control", f"public, max-age={cache_max_age}")
    h.end_headers()
    try:
        h.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _get_db():
    global _db
    if _db is None:
        from shared.db import get_db
        _db = get_db()
    return _db


def _parse_int(s, default):
    if not s:
        return default
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


def _parse_float(s, default=None):
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _get_cached(key):
    import time
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return val
    return None


def _set_cached(key, val):
    import time
    _cache[key] = (time.time(), val)


# ── Route dispatcher ──

def route(handler, method, path, query, body):
    h = handler

    if path == "/health":
        return _health(h)

    if path == "/api/health/full":
        return _health_full(h)

    if path == "/api/search/tenders":
        return _search_tenders(h, query)

    if path == "/api/tenders":
        return _list_tenders(h, query)

    if path.startswith("/api/tenders/"):
        tid = path.replace("/api/tenders/", "").strip("/")
        return _get_tender(h, tid)

    if path == "/api/stats":
        return _stats(h)

    if path == "/api/meta":
        return _meta(h)

    if path == "/api/niches":
        return _niches(h)

    if path == "/api/suggest/regions":
        return _suggest_regions(h, query)

    if path == "/api/suggest/customers":
        return _suggest_customers(h, query)

    if path == "/api/suggest/platforms":
        return _suggest_platforms(h)

    if path == "/api/suggest/purchase-methods":
        return _suggest_methods(h)

    if path == "/api/funding/meta":
        return _funding_meta(h)

    if path.startswith("/api/funding/"):
        pid = path.replace("/api/funding/", "").strip("/")
        return _funding_detail(h, pid)

    if path == "/api/funding":
        return _funding_list(h, query)

    if method == "POST" and path == "/api/subscriptions/create":
        return _subscribe_create(h, body)

    if method == "GET" and path == "/api/subscriptions/list":
        return _subscribe_list(h, query)

    if method == "DELETE" and path.startswith("/api/subscriptions/"):
        sid = path.replace("/api/subscriptions/", "").strip("/")
        return _subscribe_delete(h, sid, query)

    return _json(h, 404, {"error": "Not found"})


# ── Handlers ──

def _health(h):
    try:
        db = _get_db()
        result = db.table("tenders").select("id", count="estimated").limit(1).execute()
        _json(h, 200, {"status": "ok", "db": "connected", "tenders_count": str(result.count if result.count else "?")})
    except Exception as e:
        _json(h, 200, {"status": "degraded", "db": f"error: {str(e)[:100]}"})


def _health_full(h):
    try:
        from shared.db import get_stats_via_rpc, get_scrape_health
        stats = get_stats_via_rpc()
        logs = get_scrape_health()
        scrapers = {}
        for r in logs:
            name = r.get("scraper_name", "unknown")
            if name not in scrapers:
                scrapers[name] = r
        _json(h, 200, {
            "status": "ok", "db": "connected",
            "tenders_total": stats.get("total", 0),
            "scrapers": {k: {"last_run": v.get("started_at"), "status": v.get("status"), "tenders_found": v.get("tenders_found", 0), "error": v.get("error_message", "")} for k, v in scrapers.items()},
        }, cache_max_age=60)
    except Exception as e:
        _json(h, 200, {"status": "degraded", "error": str(e)[:100]})


def _search_tenders(h, q):
    from shared.models import SearchFilters
    from shared.db import search_tenders, count_tenders
    params = q
    filters = SearchFilters(
        query=params.get("q", "").strip() or None,
        region=params.get("region", "").strip() or None,
        niche=params.get("niche", "").strip() or None,
        law_type=(params.get("law_type") or params.get("law") or "").strip() or None,
        status=params.get("status", "active").strip() or "active",
        min_nmck=_parse_float(params.get("min_nmck")),
        max_nmck=_parse_float(params.get("max_nmck")),
        purchase_method=params.get("purchase_method", "").strip() or None,
        date_from=params.get("date_from", "").strip() or None,
        date_to=params.get("date_to", "").strip() or None,
        source_platform=params.get("source_platform", "").strip() or None,
        sort_by=params.get("sort", "created_at").strip() or "created_at",
        page=_parse_int(params.get("page"), 1),
        per_page=min(_parse_int(params.get("per_page"), 10), 50),
    )
    try:
        total = count_tenders(filters)
        pages = max(1, -(-total // filters.per_page)) if total else 1
        rows = search_tenders(filters)
        _json(h, 200, {"total": total, "page": filters.page, "pages": pages, "per_page": filters.per_page, "items": rows})
    except Exception as e:
        logger.exception("search_tenders")
        _json(h, 502, {"error": str(e)[:200]})


def _list_tenders(h, q):
    db = _get_db()
    qb = db.table("tenders").select("*", count="exact")
    status = q.get("status", "active")
    if status:
        qb = qb.eq("status", status)
    qt = q.get("q", "").strip()
    if qt:
        qb = qb.ilike("title", f"%{qt}%")
    niche = q.get("niche", "").strip()
    if niche:
        qb = qb.contains("niche_tags", [niche])
    region = q.get("region", "").strip()
    if region:
        qb = qb.ilike("customer_region", f"%{region}%")
    law = (q.get("law") or q.get("law_type") or "").strip()
    if law:
        qb = qb.eq("law_type", law)
    nmck_min = _parse_float(q.get("nmck_min"))
    if nmck_min is not None:
        qb = qb.gte("nmck", nmck_min)
    nmck_max = _parse_float(q.get("nmck_max"))
    if nmck_max is not None:
        qb = qb.lte("nmck", nmck_max)
    sort = q.get("sort", "deadline").strip()
    order_col = {"deadline": "submission_deadline", "nmck": "nmck"}.get(sort, "created_at")
    page = _parse_int(q.get("page"), 1)
    page_size = min(_parse_int(q.get("page_size"), 20), 100)
    start = (page - 1) * page_size
    try:
        res = qb.order(order_col, desc=True).range(start, start + page_size - 1).execute()
        total = getattr(res, "count", None) or len(res.data or [])
        _json(h, 200, {"items": res.data or [], "page": page, "page_size": page_size, "total": total})
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _get_tender(h, tid):
    db = _get_db()
    try:
        res = db.table("tenders").select("*").eq("id", tid).limit(1).execute()
        rows = res.data or []
        if rows:
            _json(h, 200, rows[0])
        else:
            _json(h, 404, {"error": "Not found"})
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _stats(h):
    cached = _get_cached("stats")
    if cached:
        return _json(h, 200, cached, cache_max_age=300)
    try:
        from shared.db import get_stats_via_rpc
        result = get_stats_via_rpc()
        _set_cached("stats", result)
        _json(h, 200, result, cache_max_age=300)
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _meta(h):
    cached = _get_cached("meta")
    if cached:
        return _json(h, 200, cached, cache_max_age=300)
    try:
        from shared.db import get_meta_via_rpc
        result = get_meta_via_rpc()
        _set_cached("meta", result)
        _json(h, 200, result, cache_max_age=300)
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _niches(h):
    try:
        from shared.db import get_niches
        result = get_niches()
        _json(h, 200, {"niches": result}, cache_max_age=300)
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _suggest_regions(h, q):
    qs = q.get("q", "").strip()
    if not qs:
        return _json(h, 200, {"items": RUSSIAN_REGIONS[:20]})
    filtered = [r for r in RUSSIAN_REGIONS if qs.lower() in r.lower()][:10]
    if filtered:
        return _json(h, 200, {"items": filtered})
    try:
        from shared.db import suggest_regions
        items = suggest_regions(qs, 10)
        _json(h, 200, {"items": items})
    except Exception:
        _json(h, 200, {"items": []})


def _suggest_customers(h, q):
    qs = q.get("q", "").strip()
    if len(qs) < 2:
        return _json(h, 200, {"items": []})
    try:
        from shared.db import suggest_customers
        items = suggest_customers(qs, 10)
        _json(h, 200, {"items": items})
    except Exception:
        _json(h, 200, {"items": []})


def _suggest_platforms(h):
    _json(h, 200, {"items": PLATFORMS})


def _suggest_methods(h):
    _json(h, 200, {"items": PURCHASE_METHODS})


def _funding_list(h, q):
    from shared.db import get_funding_programs
    try:
        rows, total = get_funding_programs(
            q=q.get("q", "").strip() or None,
            region=q.get("region", "").strip() or None,
            program_type=q.get("program_type", "").strip() or None,
            amount_max=_parse_float(q.get("amount_max")),
            source_platform=q.get("source_platform", "").strip() or None,
            status=q.get("status", "active").strip() or "active",
            page=_parse_int(q.get("page"), 1),
            page_size=min(_parse_int(q.get("page_size"), 12), 100),
        )
        for r in rows:
            r["program_type_label"] = PROGRAM_TYPE_LABELS.get(r.get("program_type", ""), r.get("program_type", ""))
            r["platform_label"] = DESCRIPTIVE_PLATFORM_NAMES.get(r.get("source_platform", ""), r.get("source_platform", ""))
        _json(h, 200, {"items": rows, "page": _parse_int(q.get("page"), 1), "page_size": min(_parse_int(q.get("page_size"), 12), 100), "total": total, "pages": max(1, -(-total // min(_parse_int(q.get("page_size"), 12), 100))) if total else 1})
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _funding_meta(h):
    try:
        from shared.db import get_funding_meta_via_rpc
        result = get_funding_meta_via_rpc()
        _json(h, 200, result, cache_max_age=600)
    except Exception as e:
        _json(h, 502, {"error": str(e)[:200]})


def _funding_detail(h, pid):
    from shared.db import get_funding_detail
    row = get_funding_detail(pid)
    if row:
        row["program_type_label"] = PROGRAM_TYPE_LABELS.get(row.get("program_type", ""), row.get("program_type", ""))
        row["platform_label"] = DESCRIPTIVE_PLATFORM_NAMES.get(row.get("source_platform", ""), row.get("source_platform", ""))
        _json(h, 200, row)
    else:
        _json(h, 404, {"error": "Not found"})


def _subscribe_create(h, body):
    from shared.models import SubscriptionCreate
    from shared.db import add_subscription
    email = (body.get("email") or "").strip()
    if not email or len(email) < 3 or "@" not in email:
        return _json(h, 400, {"error": "Valid email required"})
    uid = abs(hash(email)) % (10 ** 15)
    kw = body.get("keywords", "") or ""
    sub = SubscriptionCreate(
        telegram_user_id=uid, name=email,
        keywords=[k.strip() for k in kw.replace("\n", ",").split(",") if k.strip()] if kw else [],
        regions=[body.get("region", "").strip()] if body.get("region", "").strip() else [],
        min_nmck=_parse_float(body.get("min_nmck")),
        max_nmck=_parse_float(body.get("max_nmck")),
        niche_tags=[body.get("niche", "").strip()] if body.get("niche", "").strip() and body.get("niche", "").strip() != "custom" else [],
        law_types=[body.get("law_type", "").strip()] if body.get("law_type", "").strip() else [],
        okpd2_prefixes=[],
    )
    try:
        result = add_subscription(sub)
        _json(h, 201 if result else 500, {"subscription": result} if result else {"error": "Failed to create subscription"})
    except Exception as e:
        _json(h, 500, {"error": str(e)[:200]})


def _subscribe_list(h, q):
    from shared.db import get_subscriptions
    email = q.get("email", "").strip()
    if not email:
        return _json(h, 400, {"error": "email required"})
    uid = abs(hash(email)) % (10 ** 15)
    try:
        subs = get_subscriptions(uid)
        _json(h, 200, {"subscriptions": subs})
    except Exception as e:
        _json(h, 500, {"error": str(e)[:200]})


def _subscribe_delete(h, sid, q):
    from shared.db import delete_subscription
    email = q.get("email", "").strip()
    if not email:
        return _json(h, 400, {"error": "email required"})
    uid = abs(hash(email)) % (10 ** 15)
    try:
        ok = delete_subscription(sid, uid)
        _json(h, 200 if ok else 404, {"deleted": True} if ok else {"error": "Not found"})
    except Exception as e:
        _json(h, 500, {"error": str(e)[:200]})
