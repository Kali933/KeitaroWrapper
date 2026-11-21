"""Заглушка Keitaro Admin API для репетиции без боевого трекера.

Запуск:  uvicorn dev.mock_keitaro:app --port 9000
Затем в .env:  KEITARO_URL=http://localhost:9000   KEITARO_API_KEY=any

Данные живут в памяти и сбрасываются при перезапуске. В заглушке уже есть
кампания 216512 с потоками «AU -> Google» и «Offers» (как в вашем Keitaro).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import KeitaroError
from tests.fakes import FakeKeitaro

app = FastAPI(title="Mock Keitaro")
fake = FakeKeitaro()
# Названия явно помечены, чтобы заглушку нельзя было принять за настоящий Keitaro
fake.offers = [
    {"id": 18813, "name": "18813 Flexacil (как в боевом Keitaro)", "state": "active"},
    {"id": 11111, "name": "[MOCK] Demo offer A", "state": "active"},
    {"id": 11112, "name": "[MOCK] Demo offer B", "state": "active"},
    {"id": 3749, "name": "[MOCK] Demo offer C", "state": "active"},
]
PREFIX = "/admin_api/v1"


@app.exception_handler(KeitaroError)
async def not_found(_: Request, error: KeitaroError):
    return JSONResponse(status_code=404, content={"error": error.message})


@app.get(f"{PREFIX}/offers")
def offers():
    return fake.list_offers()


@app.get(f"{PREFIX}/domains")
def domains():
    return fake.list_domains()


@app.get(f"{PREFIX}/groups")
def groups(type: str = "campaigns"):
    return fake.list_groups(type)


@app.get(f"{PREFIX}/traffic_sources")
def sources():
    return fake.list_traffic_sources()


@app.get(f"{PREFIX}/campaigns")
def campaigns(limit: int = 100, offset: int = 0):
    return fake.list_campaigns(limit, offset)


@app.post(f"{PREFIX}/campaigns")
def create_campaign(payload: dict):
    return fake.create_campaign(payload)


@app.get(f"{PREFIX}/campaigns/{{campaign_id}}")
def get_campaign(campaign_id: int):
    return fake.get_campaign(campaign_id)


@app.delete(f"{PREFIX}/campaigns/{{campaign_id}}")
def delete_campaign(campaign_id: int):
    fake.delete_campaign(campaign_id)
    return JSONResponse(status_code=201, content={})


@app.get(f"{PREFIX}/campaigns/{{campaign_id}}/streams")
def streams(campaign_id: int):
    return fake.get_streams(campaign_id)


@app.post(f"{PREFIX}/streams")
def create_stream(payload: dict):
    return fake.create_stream(payload)


@app.put(f"{PREFIX}/streams/{{stream_id}}")
def update_stream(stream_id: int, payload: dict):
    return fake.update_stream(stream_id, payload)
