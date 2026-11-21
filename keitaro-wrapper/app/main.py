"""Точка входа FastAPI."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.errors import AppError
from app.routers import api

app = FastAPI(title="Keitaro wrapper")
app.include_router(api.router)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


# Фронтенд (один HTML-файл) раздаётся тем же сервером
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
