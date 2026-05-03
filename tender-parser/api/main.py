"""Точка входа FastAPI для модуля тендеров."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from api.routes_tenders import router as tenders_router
from api.routes_web_search import router as web_search_router
from api.routes_web_subscribe import router as web_subscribe_router
from api.routes_suggestions import router as suggestions_router
from api.routes_funding import router as funding_router

_CORS_RAW = os.getenv("CORS_ORIGINS", "")
if _CORS_RAW:
    _CORS_ORIGINS = [o.strip() for o in _CORS_RAW.split(",") if o.strip()]
else:
    _CORS_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://tender-pro.vercel.app",
        "https://tender-parser.vercel.app",
    ]
    logger.warning("CORS_ORIGINS not set — using default origins including Vercel domains")

app = FastAPI(title="Тендер PRO — Tenders API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(tenders_router, prefix="/api")
app.include_router(web_search_router, prefix="/api")
app.include_router(web_subscribe_router, prefix="/api")
app.include_router(suggestions_router, prefix="/api")
app.include_router(funding_router, prefix="/api")

_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.is_dir():
    app.mount("/web", StaticFiles(directory=str(_web_dir), html=True), name="web")


@app.on_event("startup")
def _validate_env() -> None:
    """Предупреждение при отсутствии критичных переменных окружения."""
    from shared.config import supabase_url, supabase_key, get_config
    if not supabase_url():
        logger.warning("SUPABASE_URL not set — DB endpoints will fail")
    if not supabase_key():
        logger.warning("SUPABASE_KEY not set — DB endpoints will fail")
    if not get_config().get("telegram_bot_token"):
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot webhook will fail")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
