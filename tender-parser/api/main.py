"""Точка входа FastAPI для модуля тендеров."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_tenders import router as tenders_router
from api.routes_web_search import router as web_search_router
from api.routes_web_subscribe import router as web_subscribe_router
from api.routes_suggestions import router as suggestions_router

_CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="Подряд PRO — Tenders API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(tenders_router, prefix="/api")
app.include_router(web_search_router, prefix="/api")
app.include_router(web_subscribe_router, prefix="/api")
app.include_router(suggestions_router, prefix="/api")

_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.is_dir():
    app.mount("/web", StaticFiles(directory=str(_web_dir), html=True), name="web")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
