"""Заглушка Keitaro для тестов: хранит данные в памяти и записывает вызовы."""

import copy

from app.errors import KeitaroError

# Реальный ответ GET /campaigns/216512/streams (кампания test_repin_campaign1)
REAL_STREAMS = [
    {
        "id": 1330994, "type": "regular", "name": "AU -> Google", "campaign_id": 216512, "position": 1,
        "action_options": None, "comments": "", "state": "active", "action_type": "http",
        "action_payload": "https://google.com", "schema": "redirect", "collect_clicks": True,
        "filter_or": False, "weight": 100, "offer_selection": "before_click",
        "filters": [{"id": 2999076, "stream_id": 1330994, "name": "country", "mode": "accept",
                     "payload": ["AU"], "oid": 2999076}],
        "triggers": [], "landings": [], "offers": [],
    },
    {
        "id": 1330995, "type": "regular", "name": "Offers", "campaign_id": 216512, "position": 2,
        "action_options": None, "comments": "", "state": "active", "action_type": "http",
        "action_payload": "", "schema": "landings", "collect_clicks": True, "filter_or": False,
        "weight": 100, "offer_selection": "before_click", "filters": [], "triggers": [], "landings": [],
        "offers": [{"id": 2086937, "stream_id": 1330995, "offer_id": 18813, "state": "active", "share": 100}],
    },
]


class FakeKeitaro:
    def __init__(self):
        self.offers = [
            {"id": 18813, "name": "Flexacil [JOINT-PE]", "state": "active"},
            {"id": 11111, "name": "FitoMishki [Weight Loss]", "state": "active"},
            {"id": 11112, "name": "Oxys [BEAUTY-CL]", "state": "active"},
            {"id": 3749, "name": "Miaflow [BEAUTY-RO-BE_0009]", "state": "active"},
        ]
        self.domains = [{"id": 1, "name": "kylovoa.com"}]
        self.groups = [{"id": 7, "name": "FORTESTS", "type": "campaigns"}]
        self.sources = [{"id": 5, "name": "FORTESTS"}]
        self.campaigns = {216512: {"id": 216512, "name": "test_repin_campaign1", "alias": "G4Lb8J"}}
        self.streams = {216512: copy.deepcopy(REAL_STREAMS)}
        self.calls: list[tuple] = []
        self.fail_on_stream_create = False
        self.ignore_updates = False  # имитация сервера, который отвечает ОК, но ничего не меняет
        self._next_id = 5000

    # --- справочники ---
    def list_offers(self):
        return copy.deepcopy(self.offers)

    def list_domains(self):
        return self.domains

    def list_groups(self, group_type="campaigns"):
        return self.groups

    def list_traffic_sources(self):
        return self.sources

    # --- кампании и потоки ---
    def list_campaigns(self, limit=100, offset=0):
        return list(self.campaigns.values())[offset:offset + limit]

    def get_campaign(self, campaign_id):
        if campaign_id not in self.campaigns:
            raise KeitaroError("Keitaro вернул 404: campaign not found")
        return self.campaigns[campaign_id]

    def create_campaign(self, payload):
        self.calls.append(("create_campaign", payload))
        campaign = {"id": self._new_id(), **payload}
        self.campaigns[campaign["id"]] = campaign
        self.streams[campaign["id"]] = []
        return campaign

    def delete_campaign(self, campaign_id):
        self.calls.append(("delete_campaign", campaign_id))
        self.campaigns.pop(campaign_id, None)
        self.streams.pop(campaign_id, None)

    def get_streams(self, campaign_id):
        return copy.deepcopy(self.streams[campaign_id])

    def create_stream(self, payload):
        self.calls.append(("create_stream", payload))
        if self.fail_on_stream_create:
            raise KeitaroError("Keitaro вернул 500: boom")
        stream = {"id": self._new_id(), "state": "active", "offers": [], "filters": [], **payload}
        self.streams[payload["campaign_id"]].append(stream)
        return stream

    def update_stream(self, stream_id, payload):
        self.calls.append(("update_stream", stream_id, payload))
        if self.ignore_updates:
            return {"id": stream_id}
        for streams in self.streams.values():
            for stream in streams:
                if stream["id"] == stream_id:
                    stream.update(payload)  # offers заменяются целиком, как в Keitaro
                    return stream
        raise KeitaroError("Keitaro вернул 404: stream not found")

    # --- помощники для тестов ---
    def kt_offers(self, stream_id):
        for streams in self.streams.values():
            for stream in streams:
                if stream["id"] == stream_id:
                    return [(o["offer_id"], o["share"]) for o in stream["offers"]]

    def calls_named(self, name):
        return [call for call in self.calls if call[0] == name]

    def _new_id(self):
        self._next_id += 1
        return self._next_id
