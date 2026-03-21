"""
Telegram webhook для Vercel Python (@vercel/python).
В начале — корень репозитория в sys.path (импорт bot/, shared/).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


class handler(BaseHTTPRequestHandler):
    """Vercel ожидает класс handler(BaseHTTPRequestHandler)."""

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            from bot.handler import process_update

            asyncio.run(process_update(data))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception:
            logger.exception("webhook POST failed")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"ERR")

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, fmt: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args if args else fmt)
