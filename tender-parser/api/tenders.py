"""Vercel Serverless Function: REST API для поиска тендеров.

GET /api/tenders?q=мебель&region=Омская+область&min_nmck=100000&page=1
"""

from __future__ import annotations

import json
import sys
import os
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import BaseHTTPRequestHandler
from shared.db import search_tenders, count_tenders
from shared.models import SearchFilters


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            filters = SearchFilters(
                query=params.get("q", [None])[0],
                region=params.get("region", [None])[0],
                min_nmck=float(params["min_nmck"][0]) if "min_nmck" in params else None,
                max_nmck=float(params["max_nmck"][0]) if "max_nmck" in params else None,
                okpd2=params.get("okpd2", [None])[0],
                niche=params.get("niche", [None])[0],
                status=params.get("status", ["active"])[0],
                law_type=params.get("law_type", [None])[0],
                page=int(params.get("page", [1])[0]),
                per_page=int(params.get("per_page", [20])[0]),
            )

            tenders = search_tenders(filters)
            total = count_tenders(filters)

            response = {
                "ok": True,
                "data": tenders,
                "total": total,
                "page": filters.page,
                "per_page": filters.per_page,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False, default=str).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
