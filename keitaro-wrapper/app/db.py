"""Подключение к базе данных (SQLAlchemy)."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_session_factory() -> sessionmaker:
    url = get_settings().database_url
    # check_same_thread нужен только SQLite: FastAPI обрабатывает запросы в разных потоках
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return sessionmaker(bind=create_engine(url, connect_args=connect_args), expire_on_commit=False)


def get_db():
    """Зависимость FastAPI: одна сессия БД на запрос."""
    db: Session = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
