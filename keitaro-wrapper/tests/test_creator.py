import pytest

from app.errors import AppError, KeitaroError
from app.services import campaign_creator
from app.models import CreatedCampaign


def create(db, keitaro, settings, **overrides):
    args = {"name": "test_repin_campaign2", "geo": "mx, au", "offer_id": 11111, **overrides}
    return campaign_creator.create_campaign(db, keitaro, settings, **args)


def test_creates_campaign_with_two_streams(db, keitaro, settings):
    result = create(db, keitaro, settings)

    (_, campaign_payload), = keitaro.calls_named("create_campaign")
    assert campaign_payload["name"] == "test_repin_campaign2"
    assert campaign_payload["domain_id"] == 1
    assert campaign_payload["group_id"] == "7"          # строка, как в схеме Keitaro
    assert campaign_payload["traffic_source_id"] == 5
    assert len(campaign_payload["alias"]) == 6

    (_, google), (_, offers) = keitaro.calls_named("create_stream")
    assert google["position"] == 1 and google["schema"] == "redirect"
    assert google["action_payload"] == "https://google.com"
    assert google["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]
    assert google["name"] == "MX, AU -> Google"
    assert offers["position"] == 2 and offers["schema"] == "landings" and "filters" not in offers
    assert offers["offers"] == [{"offer_id": 11111, "share": 100, "state": "active"}]
    assert google["campaign_id"] == offers["campaign_id"] == result["kt_id"]

    assert result["url"].startswith("https://kylovoa.com/")
    assert db.query(CreatedCampaign).count() == 1


def test_stream_failure_rolls_back_campaign(db, keitaro, settings):
    keitaro.fail_on_stream_create = True
    with pytest.raises(KeitaroError) as error:
        create(db, keitaro, settings)
    assert "архив" in error.value.message
    assert len(keitaro.calls_named("delete_campaign")) == 1
    assert db.query(CreatedCampaign).count() == 0


@pytest.mark.parametrize("raw, expected", [("mx,AU, ro", ["MX", "AU", "RO"]), ("MX;MX, au", ["MX", "AU"])])
def test_parse_geos(raw, expected):
    assert campaign_creator.parse_geos(raw) == expected


@pytest.mark.parametrize("raw", ["", " , ", "USA", "M1"])
def test_parse_geos_rejects_bad_input(raw):
    with pytest.raises(AppError):
        campaign_creator.parse_geos(raw)


def test_unknown_offer_domain_group(db, keitaro, settings):
    with pytest.raises(AppError):
        create(db, keitaro, settings, offer_id=99999)
    with pytest.raises(AppError):
        create(db, keitaro, settings.model_copy(update={"default_domain": "other.com"}))
    with pytest.raises(AppError):
        create(db, keitaro, settings.model_copy(update={"default_domain": ""}))
    with pytest.raises(AppError):
        create(db, keitaro, settings, name="  ")
    assert keitaro.calls_named("create_campaign") == []  # ничего не создано
