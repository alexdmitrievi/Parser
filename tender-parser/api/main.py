"""Точка входа FastAPI для модуля тендеров."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_tenders import router as tenders_router
from api.routes_web_search import router as web_search_router
from api.routes_web_subscribe import router as web_subscribe_router

app = FastAPI(title="Подряд PRO — Tenders API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenders_router, prefix="/api")
app.include_router(web_search_router, prefix="/api")
app.include_router(web_subscribe_router, prefix="/api")

_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.is_dir():
    app.mount("/web", StaticFiles(directory=str(_web_dir), html=True), name="web")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
