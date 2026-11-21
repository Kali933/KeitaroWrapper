"""Зависимости FastAPI."""

from app.config import Settings, get_settings
from app.errors import AppError
from app.keitaro_client import KeitaroClient


def get_client() -> KeitaroClient:
    settings = get_settings()
    if not settings.keitaro_url or not settings.keitaro_api_key:
        raise AppError("Не заданы KEITARO_URL и KEITARO_API_KEY: заполните файл .env")
    return KeitaroClient(settings.keitaro_url, settings.keitaro_api_key)


def settings_dep() -> Settings:
    return get_settings()
