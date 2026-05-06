"""
Vercel serverless handler — self-contained API router.
No FastAPI, no Starlette, no TestClient — direct calls to shared modules.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://localhost:8000,"
    "https://tender-pro.vercel.app,"
    "https://tender-parser.vercel.app"
)

DESCRIPTIVE_PLATFORM_NAMES = {
    "eis": "ЕИС", "roseltorg": "Росэлторг", "sberbank_ast": "Сбербанк-АСТ",
    "rts_tender": "РТС-тендер", "tektorg": "ТЭК-Торг", "b2b_center": "B2B-Center",
    "tenderguru": "TenderGuru", "fabrikant": "Fabrikant", "tenderpro": "TenderPro",
    "etpgpb": "ЭТП ГПБ", "etp_ets": "ЭТП ЕТС", "rostender": "Ростендер",
    "corpmsp": "Корпорация МСП", "mybusiness": "Мой Бизнес",
    "frprf": "ФРП РФ", "mspbank": "МСП Банк",
}

PROGRAM_TYPE_LABELS = {
    "grant": "Грант", "loan": "Кредит", "microloan": "Микрозайм",
    "subsidy": "Субсидия", "guarantee": "Поручительство",
    "compensation": "Компенсация", "leasing": "Лизинг",
}

PURCHASE_METHODS = ["Аукцион", "Конкурс", "Запрос котировок", "Запрос предложений", "Единственный поставщик", "Открытый аукцион"]

PLATFORMS = [
    {"id": "eis", "name": "ЕИС"},
    {"id": "roseltorg", "name": "Росэлторг"},
    {"id": "sberbank_ast", "name": "Сбербанк-АСТ"},
    {"id": "rts_tender", "name": "РТС-тендер"},
    {"id": "tektorg", "name": "ТЭК-Торг"},
    {"id": "b2b_center", "name": "B2B-Center"},
    {"id": "tenderguru", "name": "TenderGuru"},
    {"id": "fabrikant", "name": "Fabrikant"},
    {"id": "tenderpro", "name": "TenderPro"},
    {"id": "etpgpb", "name": "ЭТП ГПБ"},
    {"id": "etp_ets", "name": "ЭТП ЕТС"},
    {"id": "rostender", "name": "Ростендер"},
]

RUSSIAN_REGIONS = [
    "Алтайский край", "Амурская область", "Архангельская область",
    "Астраханская область", "Белгородская область", "Брянская область",
    "Владимирская область", "Волгоградская область", "Вологодская область",
    "Воронежская область", "Еврейская АО", "Забайкальский край",
    "Ивановская область", "Иркутская область", "Кабардино-Балкария",
    "Калининградская область", "Калужская область", "Камчатский край",
    "Карачаево-Черкесия", "Кемеровская область", "Кировская область",
    "Костромская область", "Краснодарский край", "Красноярский край",
    "Курганская область", "Курская область", "Ленинградская область",
    "Липецкая область", "Магаданская область", "Москва",
    "Московская область", "Мурманская область", "Ненецкий АО",
    "Нижегородская область", "Новгородская область", "Новосибирская область",
    "Омская область", "Оренбургская область", "Орловская область",
    "Пензенская область", "Пермский край", "Приморский край",
    "Псковская область", "Республика Адыгея", "Республика Алтай",
    "Республика Башкортостан", "Республика Бурятия", "Республика Дагестан",
    "Республика Ингушетия", "Республика Калмыкия", "Республика Карелия",
    "Республика Коми", "Республика Крым", "Республика Марий Эл",
    "Республика Мордовия", "Республика Саха (Якутия)",
    "Республика Северная Осетия — Алания", "Республика Татарстан",
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

try:
    from shared.db import (
        get_db, search_tenders, count_tenders, suggest_regions, suggest_customers,
        get_subscriptions, add_subscription, delete_subscription,
        count_user_subscriptions, get_stats_via_rpc, get_meta_via_rpc,
        get_funding_programs, get_funding_detail, get_funding_meta_via_rpc,
        get_niches, get_scrape_health, check_rate_limit,
    )
    from shared.models import SearchFilters, SubscriptionCreate
    from shared.config import supabase_url, supabase_key
    MODULES_OK = True
except Exception as e:
    logger.error(f"Import failed: {e}")
    MODULES_OK = False


def _json(handler, status, data, cache_max_age=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    if cache_max_age:
        handler.send_header("Cache-Control", f"public, max-age={cache_max_age}")
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _cors_preflight(handler):
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
    handler.send_header("Access-Control-Max-Age", "86400")
    handler.end_headers()


def _parse_qs(query_string: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(query_string).items()}


def _read_body(handler) -> bytes:
    length = int(handler.headers.get("Content-Length", 0))
    return handler.rfile.read(length) if length > 0 else b""


def _parse_body_json(handler) -> dict:
    raw = _read_body(handler)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _parse_int(s: str | None, default: int) -> int:
    if not s:
        return default
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


def _parse_float(s: str | None, default: float | None = None) -> float | None:
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _get_client_ip(handler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.client_address[0] if handler.client_address else "0.0.0.0"


def _check_rate_limit(handler) -> bool:
    ip = _get_client_ip(handler)
    path = handler.path.split("?")[0]
    endpoint = path.split("/")[2] if len(path.split("/")) > 2 else "general"
    try:
        return check_rate_limit(ip, endpoint, max_requests=30, window_seconds=60)
    except Exception:
        return True


# ── Route handlers ──


def _health(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"status": "degraded", "db": "modules not loaded"})
        return
    try:
        db = get_db()
        result = db.table("tenders").select("id", count="estimated").limit(1).execute()
        _json(handler, 200, {
            "status": "ok", "db": "connected",
            "tenders_count": str(result.count if result.count else "?"),
        })
    except Exception as e:
        _json(handler, 200, {"status": "degraded", "db": f"error: {str(e)[:100]}"})


def _health_full(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"status": "degraded"})
        return
    try:
        stats = get_stats_via_rpc()
        scrape_rows = get_scrape_health()
        scrapers = {}
        for r in scrape_rows:
            name = r.get("scraper_name", "unknown")
            if name not in scrapers:
                scrapers[name] = r
        _json(handler, 200, {
            "status": "ok",
            "db": "connected",
            "tenders_total": stats.get("total", 0),
            "scrapers": {k: {
                "last_run": v.get("started_at"),
                "status": v.get("status"),
                "tenders_found": v.get("tenders_found", 0),
                "error": v.get("error_message", ""),
            } for k, v in scrapers.items()},
        }, cache_max_age=60)
    except Exception as e:
        _json(handler, 200, {"status": "degraded", "error": str(e)[:100]})


def _search_tenders(handler, params: dict) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    q = params.get("q", "").strip() or None
    filters = SearchFilters(
        query=q,
        region=params.get("region", "").strip() or None,
        niche=params.get("niche", "").strip() or None,
        law_type=params.get("law_type", params.get("law", "")).strip() or None,
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
    except Exception as e:
        logger.exception("search_tenders failed")
        _json(handler, 502, {"error": str(e)[:200]})
        return
    _json(handler, 200, {
        "total": total, "page": filters.page, "pages": pages,
        "per_page": filters.per_page, "items": rows,
    })


def _list_tenders(handler, params: dict) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    db = get_db()
    qb = db.table("tenders").select("*", count="exact")
    status = params.get("status", "active")
    if status:
        qb = qb.eq("status", status)
    q = params.get("q", "").strip()
    if q:
        qb = qb.ilike("title", f"%{q}%")
    niche = params.get("niche", "").strip()
    if niche:
        qb = qb.contains("niche_tags", [niche])
    region = params.get("region", "").strip()
    if region:
        qb = qb.ilike("customer_region", f"%{region}%")
    law = params.get("law", params.get("law_type", "")).strip()
    if law:
        qb = qb.eq("law_type", law)
    nmck_min = _parse_float(params.get("nmck_min"))
    if nmck_min is not None:
        qb = qb.gte("nmck", nmck_min)
    nmck_max = _parse_float(params.get("nmck_max"))
    if nmck_max is not None:
        qb = qb.lte("nmck", nmck_max)
    sort = params.get("sort", "deadline").strip()
    order_col = {"deadline": "submission_deadline", "nmck": "nmck"}.get(sort, "created_at")
    page = _parse_int(params.get("page"), 1)
    page_size = min(_parse_int(params.get("page_size"), 20), 100)
    start = (page - 1) * page_size
    try:
        res = qb.order(order_col, desc=True).range(start, start + page_size - 1).execute()
        total = getattr(res, "count", None) or len(res.data or [])
        _json(handler, 200, {
            "items": res.data or [], "page": page,
            "page_size": page_size, "total": total,
        })
    except Exception as e:
        logger.exception("list_tenders failed")
        _json(handler, 502, {"error": str(e)[:200]})


def _get_tender(handler, tender_id: str) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    db = get_db()
    try:
        res = db.table("tenders").select("*").eq("id", tender_id).limit(1).execute()
        rows = res.data or []
        if rows:
            _json(handler, 200, rows[0])
        else:
            _json(handler, 404, {"error": "Not found"})
    except Exception as e:
        logger.exception("get_tender failed")
        _json(handler, 502, {"error": str(e)[:200]})


def _stats(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    try:
        result = get_stats_via_rpc()
        _json(handler, 200, result, cache_max_age=300)
    except Exception as e:
        logger.exception("stats failed")
        _json(handler, 502, {"error": str(e)[:200]})


def _meta(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    try:
        result = get_meta_via_rpc()
        _json(handler, 200, result, cache_max_age=300)
    except Exception as e:
        logger.exception("meta failed")
        _json(handler, 502, {"error": str(e)[:200]})


def _niches(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    try:
        result = get_niches()
        _json(handler, 200, {"niches": result}, cache_max_age=300)
    except Exception as e:
        _json(handler, 502, {"error": str(e)[:200]})


def _suggest_regions(handler, params: dict) -> None:
    q = params.get("q", "").strip()
    if not q:
        _json(handler, 200, {"items": RUSSIAN_REGIONS[:20]})
        return
    filtered = [r for r in RUSSIAN_REGIONS if q.lower() in r.lower()][:10]
    if filtered:
        _json(handler, 200, {"items": filtered})
        return
    if MODULES_OK:
        try:
            items = suggest_regions(q, 10)
            _json(handler, 200, {"items": items})
            return
        except Exception:
            pass
    _json(handler, 200, {"items": []})


def _suggest_customers(handler, params: dict) -> None:
    q = params.get("q", "").strip()
    if len(q) < 2 or not MODULES_OK:
        _json(handler, 200, {"items": []})
        return
    try:
        items = suggest_customers(q, 10)
        _json(handler, 200, {"items": items})
    except Exception as e:
        _json(handler, 200, {"items": []})


def _suggest_platforms(handler) -> None:
    _json(handler, 200, {"items": PLATFORMS})


def _suggest_purchase_methods(handler) -> None:
    _json(handler, 200, {"items": PURCHASE_METHODS})


def _funding_list(handler, params: dict) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    q = params.get("q", "").strip() or None
    region = params.get("region", "").strip() or None
    program_type = params.get("program_type", "").strip() or None
    industry = params.get("industry", "").strip() or None
    amount_max = _parse_float(params.get("amount_max"))
    source_platform = params.get("source_platform", "").strip() or None
    status = params.get("status", "active").strip() or "active"
    page = _parse_int(params.get("page"), 1)
    page_size = min(_parse_int(params.get("page_size"), 12), 100)
    try:
        rows, total = get_funding_programs(
            q=q, region=region, program_type=program_type,
            industry=industry, amount_max=amount_max,
            source_platform=source_platform, status=status,
            page=page, page_size=page_size,
        )
        # Add labels
        for r in rows:
            r["program_type_label"] = PROGRAM_TYPE_LABELS.get(r.get("program_type", ""), r.get("program_type", ""))
            r["platform_label"] = DESCRIPTIVE_PLATFORM_NAMES.get(r.get("source_platform", ""), r.get("source_platform", ""))
        _json(handler, 200, {
            "items": rows, "page": page, "page_size": page_size,
            "total": total, "pages": max(1, -(-total // page_size)) if total else 1,
        })
    except Exception as e:
        logger.exception("funding_list failed")
        _json(handler, 502, {"error": str(e)[:200]})


def _funding_meta(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    try:
        result = get_funding_meta_via_rpc()
        _json(handler, 200, result, cache_max_age=600)
    except Exception as e:
        _json(handler, 502, {"error": str(e)[:200]})


def _funding_detail(handler, program_id: str) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    row = get_funding_detail(program_id)
    if row:
        row["program_type_label"] = PROGRAM_TYPE_LABELS.get(row.get("program_type", ""), row.get("program_type", ""))
        row["platform_label"] = DESCRIPTIVE_PLATFORM_NAMES.get(row.get("source_platform", ""), row.get("source_platform", ""))
        _json(handler, 200, row)
    else:
        _json(handler, 404, {"error": "Not found"})


def _subscribe_create(handler) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    try:
        body = _parse_body_json(handler)
    except json.JSONDecodeError:
        _json(handler, 400, {"error": "Invalid JSON body"})
        return
    email = (body.get("email") or "").strip()
    if not email or len(email) < 3 or len(email) > 320 or "@" not in email:
        _json(handler, 400, {"error": "Valid email required"})
        return
    uid = hash(email) % (10 ** 15)
    if uid < 0:
        uid = -uid
    keywords_raw = body.get("keywords", "") or ""
    sub = SubscriptionCreate(
        telegram_user_id=uid,
        name=email,
        keywords=[k.strip() for k in keywords_raw.replace("\n", ",").split(",") if k.strip()] if keywords_raw else [],
        regions=[body["region"].strip()] if body.get("region", "").strip() else [],
        min_nmck=_parse_float(body.get("min_nmck")),
        max_nmck=_parse_float(body.get("max_nmck")),
        niche_tags=[body["niche"].strip()] if body.get("niche", "").strip() and body.get("niche", "").strip() != "custom" else [],
        law_types=[body["law_type"].strip()] if body.get("law_type", "").strip() else [],
        okpd2_prefixes=[],
    )
    try:
        result = add_subscription(sub)
        if result:
            _json(handler, 201, {"subscription": result})
        else:
            _json(handler, 500, {"error": "Failed to create subscription"})
    except Exception as e:
        _json(handler, 500, {"error": str(e)[:200]})


def _subscribe_list(handler, params: dict) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    email = params.get("email", "").strip()
    if not email:
        _json(handler, 400, {"error": "email parameter required"})
        return
    uid = hash(email) % (10 ** 15)
    if uid < 0:
        uid = -uid
    try:
        subs = get_subscriptions(uid)
        _json(handler, 200, {"subscriptions": subs})
    except Exception as e:
        _json(handler, 500, {"error": str(e)[:200]})


def _subscribe_delete(handler, sub_id: str, params: dict) -> None:
    if not MODULES_OK:
        _json(handler, 503, {"error": "modules not loaded"})
        return
    email = params.get("email", "").strip()
    if not email:
        _json(handler, 400, {"error": "email parameter required"})
        return
    uid = hash(email) % (10 ** 15)
    if uid < 0:
        uid = -uid
    try:
        ok = delete_subscription(sub_id, uid)
        if ok:
            _json(handler, 200, {"deleted": True})
        else:
            _json(handler, 404, {"error": "Not found"})
    except Exception as e:
        _json(handler, 500, {"error": str(e)[:200]})


# ── Main handler ──


class handler(BaseHTTPRequestHandler):
    """Vercel @vercel/python entry point."""

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        _cors_preflight(self)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        params = _parse_qs(parsed.query)

        if not _check_rate_limit(self):
            _json(self, 429, {"error": "rate_limited", "detail": "Too many requests"})
            return

        try:
            if path == "/health":
                return _health(self)

            if path == "/api/health/full":
                return _health_full(self)

            if path == "/api/search/tenders":
                return _search_tenders(self, params)

            if path == "/api/tenders":
                return _list_tenders(self, params)

            if path.startswith("/api/tenders/"):
                tender_id = path.replace("/api/tenders/", "").strip("/")
                return _get_tender(self, tender_id)

            if path == "/api/stats":
                return _stats(self)

            if path == "/api/meta":
                return _meta(self)

            if path == "/api/niches":
                return _niches(self)

            if path == "/api/suggest/regions":
                return _suggest_regions(self, params)

            if path == "/api/suggest/customers":
                return _suggest_customers(self, params)

            if path == "/api/suggest/platforms":
                return _suggest_platforms(self)

            if path == "/api/suggest/purchase-methods":
                return _suggest_purchase_methods(self)

            if path == "/api/funding/meta":
                return _funding_meta(self)

            if path.startswith("/api/funding/"):
                program_id = path.replace("/api/funding/", "").strip("/")
                return _funding_detail(self, program_id)

            if path == "/api/funding":
                return _funding_list(self, params)

            if method == "POST" and path == "/api/subscriptions/create":
                return _subscribe_create(self)

            if method == "GET" and path == "/api/subscriptions/list":
                return _subscribe_list(self, params)

            if method == "DELETE" and path.startswith("/api/subscriptions/"):
                sub_id = path.replace("/api/subscriptions/", "").strip("/")
                return _subscribe_delete(self, sub_id, params)

            _json(self, 404, {"error": "Not found"})

        except Exception:
            logger.exception("dispatch error: %s %s", method, path)
            _json(self, 500, {"error": "Internal server error"})

    def log_message(self, fmt: str, *args: object) -> None:
        pass
