"""
Vercel serverless handler — minimal entry point.
Routes requests to api._routes module.
"""
import json
import logging
import sys
import os
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)


def _json_response(handler, status, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            self._dispatch("GET")
        except Exception:
            logger.exception("dispatch GET")
            _json_response(self, 500, {"error": "Internal server error"})

    def do_POST(self):
        try:
            self._dispatch("POST")
        except Exception:
            logger.exception("dispatch POST")
            _json_response(self, 500, {"error": "Internal server error"})

    def do_DELETE(self):
        try:
            self._dispatch("DELETE")
        except Exception:
            logger.exception("dispatch DELETE")
            _json_response(self, 500, {"error": "Internal server error"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length > 0 else b""

    def _parse_qs(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _dispatch(self, method):
        from api._routes import route
        parsed = urlparse(self.path)
        query = self._parse_qs()
        body_raw = self._read_body() if method in ("POST",) else None
        body = json.loads(body_raw.decode("utf-8")) if body_raw else {}
        route(self, method, parsed.path, query, body)

    def log_message(self, fmt, *args):
        pass
