"""Диагностика: показывает ошибки импорта, конфигурации и БД."""

from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        info = {
            "python": sys.version,
            "root": _ROOT,
            "env_supabase_url": bool(os.getenv("SUPABASE_URL")),
            "env_supabase_key": bool(os.getenv("SUPABASE_KEY")),
            "imports": {},
            "db_test": None,
            "mangum_test": None,
        }

        # Test imports
        for mod in ["mangum", "fastapi", "supabase", "httpx", "pydantic"]:
            try:
                __import__(mod)
                info["imports"][mod] = "ok"
            except Exception as e:
                info["imports"][mod] = str(e)

        # Test actual DB query
        try:
            from shared.config import supabase_url, supabase_key
            from supabase import create_client
            url, key = supabase_url(), supabase_key()
            cli = create_client(url, key)
            res = cli.table("tenders").select("id", count="exact").limit(1).execute()
            count = getattr(res, "count", None)
            rows = len(res.data) if res.data else 0
            info["db_test"] = {"status": "ok", "total_tenders": count, "rows_returned": rows}
        except Exception as e:
            info["db_test"] = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

        # Test Mangum + FastAPI
        try:
            from api.main import app
            from mangum import Mangum
            m = Mangum(app, lifespan="off")
            # Simulate a request to /health
            test_event = {
                "httpMethod": "GET",
                "path": "/health",
                "headers": {"host": "test"},
                "queryStringParameters": None,
                "body": None,
                "isBase64Encoded": False,
                "requestContext": {"http": {"method": "GET", "path": "/health"}},
                "version": "2.0",
                "rawPath": "/health",
                "rawQueryString": "",
            }
            result = m(test_event, None)
            info["mangum_test"] = {"status": "ok", "response": result}
        except Exception as e:
            info["mangum_test"] = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(info, indent=2, default=str).encode())

    def log_message(self, fmt, *args):
        pass
