from tests.conftest import CAMPAIGN, OFFERS_STREAM


def offers_of(state):
    stream = next(s for s in state["streams"] if s["kt_id"] == OFFERS_STREAM)
    return [(o["offer_id"], o["share"], o["status"]) for o in stream["offers"]], stream["dirty"]


def test_full_editor_flow_over_http(api, keitaro):
    state = api.post(f"/api/editor/{CAMPAIGN}/fetch").json()
    assert state["name"] == "test_repin_campaign1"
    assert state["view_url"] == f"https://tlgk.host/admin/#!/campaigns/{CAMPAIGN}"

    state = api.post(f"/api/streams/{OFFERS_STREAM}/offers", json={"offer_id": 11111}).json()
    assert offers_of(state) == ([(18813, 50, "active"), (11111, 50, "active")], True)

    state = api.delete(f"/api/streams/{OFFERS_STREAM}/offers/18813").json()
    assert offers_of(state) == ([(11111, 100, "active"), (18813, 0, "removed")], True)

    state = api.post(f"/api/streams/{OFFERS_STREAM}/push").json()
    assert offers_of(state)[1] is False
    assert keitaro.kt_offers(OFFERS_STREAM) == [(11111, 100)]

    state = api.get(f"/api/editor/{CAMPAIGN}").json()
    assert offers_of(state)[0][-1] == (18813, 0, "removed")


def test_pin_and_cancel_over_http(api):
    api.post(f"/api/editor/{CAMPAIGN}/fetch")
    api.post(f"/api/streams/{OFFERS_STREAM}/offers", json={"offer_id": 11111})
    state = api.put(f"/api/streams/{OFFERS_STREAM}/offers/18813/pin", json={"share": 70}).json()
    assert offers_of(state)[0] == [(18813, 70, "active"), (11111, 30, "active")]
    state = api.post(f"/api/streams/{OFFERS_STREAM}/cancel").json()
    assert offers_of(state) == ([(18813, 100, "active")], False)


def test_info_shows_connected_keitaro(api):
    assert api.get("/api/info").json() == {
        "keitaro_url": "https://tlgk.host", "campaign_prefix": "", "api_key": "…test (4 симв.)",
    }


def test_errors_are_json_with_proper_status(api):
    assert api.get(f"/api/editor/{CAMPAIGN}").status_code == 404           # ещё не загружали
    api.post(f"/api/editor/{CAMPAIGN}/fetch")
    response = api.post(f"/api/streams/{OFFERS_STREAM}/offers", json={"offer_id": 18813})
    assert response.status_code == 409 and "уже есть" in response.json()["detail"]
    assert api.put(f"/api/streams/{OFFERS_STREAM}/offers/18813/pin", json={"share": 150}).status_code == 422
    assert api.post("/api/editor/1/fetch").status_code == 502               # Keitaro ответил ошибкой


def test_offer_search_and_campaign_creation(api, keitaro):
    found = api.get("/api/offers", params={"q": "oxys"}).json()
    assert found == [{"id": 11112, "name": "Oxys [BEAUTY-CL]"}]
    assert api.get("/api/offers", params={"q": "3749"}).json()[0]["id"] == 3749

    response = api.post("/api/campaigns", json={"name": "test_repin_c3", "geo": "ro", "offer_id": 3749})
    assert response.status_code == 200 and response.json()["geos"] == ["RO"]

    bad = api.post("/api/campaigns", json={"name": "x", "geo": "romania", "offer_id": 3749})
    assert bad.status_code == 400

    remote = api.get("/api/campaigns/remote", params={"q": "repin"}).json()
    assert {"id": CAMPAIGN, "name": "test_repin_campaign1"} in remote
