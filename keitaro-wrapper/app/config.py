"""Настройки приложения: читаются из переменных окружения и файла .env."""

import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ENV_FILE позволяет запускать приложение с другим файлом настроек (например, для заглушки Keitaro)
    model_config = SettingsConfigDict(env_file=os.getenv("ENV_FILE", ".env"), extra="ignore")

    keitaro_url: str = ""
    keitaro_api_key: str = ""

    default_domain: str = ""
    default_group: str = "FORTESTS"
    default_source: str = "FORTESTS"
    redirect_url: str = "https://google.com"

    # Защита общего аккаунта: работаем только с кампаниями, чьё название начинается с этого префикса
    campaign_name_prefix: str = ""

    database_url: str = "sqlite:///./adrobot.db"

    @field_validator("keitaro_url", "keitaro_api_key", mode="before")
    @classmethod
    def strip_noise(cls, value):
        """Убирает пробелы, кавычки и скобки <>, которые часто попадают при копировании из инструкции."""
        return value.strip().strip("\"'<>").strip() if isinstance(value, str) else value


def get_settings() -> Settings:
    """Читаем настройки заново при каждом обращении: правка .env действует без перезапуска сервера."""
    return Settings()
