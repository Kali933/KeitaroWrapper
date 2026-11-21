import httpx
import pytest

from app.errors import KeitaroError
from app.keitaro_client import KeitaroClient


def make_client(handler):
    return KeitaroClient("https://tlgk.host/", "secret", transport=httpx.MockTransport(handler))


def test_sends_api_key_and_uses_admin_api_path():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["Api-Key"]
        return httpx.Response(200, json=[{"id": 1}])

    assert make_client(handler).list_groups("campaigns") == [{"id": 1}]
    assert seen == {"url": "https://tlgk.host/admin_api/v1/groups?type=campaigns", "key": "secret"}


def test_update_stream_uses_put_with_json_body():
    def handler(request):
        assert request.method == "PUT" and request.url.path == "/admin_api/v1/streams/55"
        assert request.read() == b'{"offers":[{"offer_id":1,"share":100}]}'
        return httpx.Response(200, json={"id": 55})

    make_client(handler).update_stream(55, {"offers": [{"offer_id": 1, "share": 100}]})


def test_http_error_becomes_keitaro_error():
    client = make_client(lambda request: httpx.Response(400, text="bad request"))
    with pytest.raises(KeitaroError, match="400"):
        client.get_campaign(1)


def test_rejected_api_key_has_actionable_message():
    client = make_client(lambda request: httpx.Response(401, text="INVALID API KEY"))
    with pytest.raises(KeitaroError, match="KEITARO_API_KEY"):
        client.list_offers()


def test_network_error_becomes_keitaro_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(KeitaroError, match="Нет связи"):
        make_client(handler).list_offers()
