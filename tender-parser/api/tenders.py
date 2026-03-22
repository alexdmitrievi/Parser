"""
Vercel serverless: FastAPI через BaseHTTPRequestHandler + TestClient.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

from api.main import app
from starlette.testclient import TestClient

_client = TestClient(app, raise_server_exceptions=False)


class handler(BaseHTTPRequestHandler):

    def _proxy(self, method: str) -> None:
        url = self.path  # уже содержит path + query string

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Только нужные заголовки, без Host/Connection которые ломают TestClient
        safe_headers = {}
        ct = self.headers.get("Content-Type")
        if ct:
            safe_headers["Content-Type"] = ct
        accept = self.headers.get("Accept")
        if accept:
            safe_headers["Accept"] = accept

        try:
            if method == "GET":
                resp = _client.get(url, headers=safe_headers)
            elif method == "POST":
                resp = _client.post(url, content=body, headers=safe_headers)
            elif method == "DELETE":
                resp = _client.delete(url, headers=safe_headers)
            elif method == "OPTIONS":
                resp = _client.options(url, headers=safe_headers)
            else:
                resp = _client.get(url, headers=safe_headers)

            self.send_response(resp.status_code)
            for key, val in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                    self.send_header(key, val)
            out = resp.content
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception("proxy error")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "traceback": tb}).encode())

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
