import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import get_db
from app.main import app
from app.models import Base
from app.routers.deps import get_client, settings_dep
from tests.fakes import FakeKeitaro

OFFERS_STREAM = 1330995   # поток «Offers» из реального примера
CAMPAIGN = 216512


@pytest.fixture
def settings():
    return Settings(
        keitaro_url="https://tlgk.host", keitaro_api_key="test",
        default_domain="https://kylovoa.com/", default_group="FORTESTS", default_source="FORTESTS",
        redirect_url="https://google.com", campaign_name_prefix="",  # явно, чтобы не зависеть от окружения
        _env_file=None,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def keitaro():
    return FakeKeitaro()


@pytest.fixture
def api(db, keitaro, settings):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_client] = lambda: keitaro
    app.dependency_overrides[settings_dep] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()
