"""Диагностика: показывает ошибки импорта и конфигурации."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        info = {
            "python": sys.version,
            "root": _ROOT,
            "sys_path": sys.path[:5],
            "env_supabase_url": bool(os.getenv("SUPABASE_URL")),
            "env_supabase_key": bool(os.getenv("SUPABASE_KEY")),
            "env_telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "imports": {},
        }

        for mod in ["mangum", "fastapi", "supabase", "httpx", "pydantic", "starlette"]:
            try:
                __import__(mod)
                info["imports"][mod] = "ok"
            except Exception as e:
                info["imports"][mod] = str(e)

        try:
            from shared.config import supabase_url, supabase_key
            info["imports"]["shared.config"] = "ok"
            info["supabase_url_value"] = supabase_url()[:30] + "..." if supabase_url() else "EMPTY"
        except Exception as e:
            info["imports"]["shared.config"] = str(e)

        try:
            from shared.db import get_db
            info["imports"]["shared.db"] = "ok"
        except Exception as e:
            info["imports"]["shared.db"] = str(e)

        try:
            from bot.messages import format_tender_card
            info["imports"]["bot.messages"] = "ok"
        except Exception as e:
            info["imports"]["bot.messages"] = str(e)

        try:
            from api.main import app
            info["imports"]["api.main"] = "ok"
            info["routes"] = [r.path for r in app.routes][:20]
        except Exception as e:
            info["imports"]["api.main"] = str(e)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(info, indent=2, default=str).encode())

    def log_message(self, fmt, *args):
        pass
