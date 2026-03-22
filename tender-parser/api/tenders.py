"""
Vercel serverless: FastAPI через WSGI-адаптер (BaseHTTPRequestHandler).
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

# Импорт FastAPI приложения
from api.main import app
from starlette.testclient import TestClient

_client = TestClient(app, raise_server_exceptions=False)


class handler(BaseHTTPRequestHandler):
    """Проксирует HTTP-запросы в FastAPI через TestClient."""

    def _proxy(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query

        url = path
        if query:
            url = f"{path}?{query}"

        # Читаем тело запроса если есть
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Собираем заголовки
        headers = {}
        for key in self.headers:
            headers[key] = self.headers[key]

        try:
            if method == "GET":
                resp = _client.get(url, headers=headers)
            elif method == "POST":
                resp = _client.post(url, content=body, headers=headers)
            elif method == "DELETE":
                resp = _client.delete(url, headers=headers)
            elif method == "OPTIONS":
                resp = _client.options(url, headers=headers)
            else:
                resp = _client.get(url, headers=headers)

            self.send_response(resp.status_code)
            for key, val in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                    self.send_header(key, val)
            body_bytes = resp.content
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
        except Exception:
            logger.exception("proxy error")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Internal server error"}).encode())

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")

    def do_DELETE(self) -> None:
        self._proxy("DELETE")

    def do_OPTIONS(self) -> None:
        self._proxy("OPTIONS")

    def log_message(self, fmt: str, *args: object) -> None:
        pass
