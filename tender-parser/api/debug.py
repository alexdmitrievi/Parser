"""Диагностика: проверка импортов, БД и FastAPI."""

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
            "env_supabase_url": bool(os.getenv("SUPABASE_URL")),
            "env_supabase_key": bool(os.getenv("SUPABASE_KEY")),
            "imports": {},
            "db_test": None,
            "fastapi_test": None,
        }

        for mod in ["fastapi", "supabase", "httpx", "pydantic", "starlette"]:
            try:
                __import__(mod)
                info["imports"][mod] = "ok"
            except Exception as e:
                info["imports"][mod] = str(e)

        # Test DB
        try:
            from shared.config import supabase_url, supabase_key
            from supabase import create_client
            cli = create_client(supabase_url(), supabase_key())
            res = cli.table("tenders").select("id", count="exact").limit(1).execute()
            info["db_test"] = {"status": "ok", "total_tenders": getattr(res, "count", 0)}
        except Exception as e:
            info["db_test"] = {"status": "error", "error": str(e)}

        # Test FastAPI via TestClient
        try:
            from api.main import app
            from starlette.testclient import TestClient
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
            info["fastapi_test"] = {
                "status": "ok",
                "health_status_code": resp.status_code,
                "health_body": resp.json(),
            }
            # Test search endpoint
            resp2 = client.get("/api/search/tenders?page=1&per_page=1&status=active")
            info["search_test"] = {
                "status_code": resp2.status_code,
                "body": resp2.json() if resp2.status_code < 500 else resp2.text[:500],
            }
        except Exception as e:
            info["fastapi_test"] = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(info, indent=2, default=str).encode())

    def log_message(self, fmt, *args):
        pass
