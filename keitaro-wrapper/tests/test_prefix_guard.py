"""Защита от правки чужих кампаний на общем аккаунте Keitaro."""

import pytest

from app.errors import ForbiddenError
from app.routers.deps import settings_dep
from app.services import campaign_creator, editor
from tests.conftest import CAMPAIGN, OFFERS_STREAM

PREFIX = "test_repin_"


def test_fetch_refuses_foreign_campaign(db, keitaro):
    keitaro.campaigns[777] = {"id": 777, "name": "someone_elses_campaign", "alias": "X"}
    keitaro.streams[777] = []
    with pytest.raises(ForbiddenError):
        editor.fetch_campaign(db, keitaro, 777, PREFIX)


def test_fetch_allows_own_campaign(db, keitaro):
    assert editor.fetch_campaign(db, keitaro, CAMPAIGN, PREFIX).name == "test_repin_campaign1"


def test_push_is_blocked_if_campaign_was_loaded_without_guard(db, keitaro):
    editor.fetch_campaign(db, keitaro, CAMPAIGN)              # загрузили, когда защиты ещё не было
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    with pytest.raises(ForbiddenError):
        editor.push(db, keitaro, OFFERS_STREAM, "other_prefix_")
    assert keitaro.calls_named("update_stream") == []         # в Keitaro ничего не ушло


def test_creator_requires_prefix_before_touching_keitaro(db, keitaro, settings):
    guarded = settings.model_copy(update={"campaign_name_prefix": PREFIX})
    with pytest.raises(ForbiddenError):
        campaign_creator.create_campaign(db, keitaro, guarded, "my_campaign", "AU", 11111)
    assert keitaro.calls_named("create_campaign") == []
    campaign_creator.create_campaign(db, keitaro, guarded, "test_repin_ok", "AU", 11111)
    assert len(keitaro.calls_named("create_campaign")) == 1


def test_api_returns_403_and_filters_campaign_list(api, keitaro, settings):
    keitaro.campaigns[777] = {"id": 777, "name": "someone_elses_campaign", "alias": "X"}
    keitaro.streams[777] = []
    api.app.dependency_overrides[settings_dep] = lambda: settings.model_copy(update={"campaign_name_prefix": PREFIX})

    assert api.post("/api/editor/777/fetch").status_code == 403
    assert api.post(f"/api/editor/{CAMPAIGN}/fetch").status_code == 200
    names = [c["name"] for c in api.get("/api/campaigns/remote").json()]
    assert names == ["test_repin_campaign1"]                  # чужая кампания не показывается
