"""
Telegram webhook for Vercel Python (@vercel/python).
"""
import asyncio
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            from shared.config import get_config
            secret = get_config().get("bot_webhook_secret", "")
            if not secret:
                logger.warning("BOT_WEBHOOK_SECRET not set")
                self._text(503, "Webhook disabled")
                return

            token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if token != secret:
                self._text(401, "Unauthorized")
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            from bot.handler import process_update
            _run_async(process_update(data))
            self._text(200, "OK")
        except Exception:
            logger.exception("webhook POST failed")
            self._text(500, "ERR")

    def do_GET(self):
        self._text(200, '{"ok":true}')

    def _text(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    def log_message(self, fmt, *args):
        pass
