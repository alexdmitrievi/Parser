"""Vercel Serverless Function: Telegram webhook handler.

POST /api/webhook — принимает Update от Telegram.
"""

from __future__ import annotations

import json
import logging
import sys
import os

# Добавляем корень проекта в path для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless handler."""

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            update = json.loads(body)

            logger.info(f"Received update: {update.get('update_id', '?')}")

            from bot.handler import handle_update
            handle_update(update)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            self.send_response(200)  # Всегда 200, чтобы Telegram не ретраил
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        """Health check."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "Tender Parser Bot is running"}')
