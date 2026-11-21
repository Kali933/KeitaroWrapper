"""Клиент Keitaro Admin API. Единственное место, где приложение ходит в Keitaro."""

import httpx

from app.errors import KeitaroError


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30, transport=None):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/admin_api/v1",
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,  # в тестах сюда подставляется заглушка
        )

    # --- чтение справочников ---

    def list_offers(self) -> list[dict]:
        return self._request("GET", "/offers")

    def list_domains(self) -> list[dict]:
        return self._request("GET", "/domains")

    def list_groups(self, group_type: str = "campaigns") -> list[dict]:
        return self._request("GET", "/groups", params={"type": group_type})

    def list_traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources")

    # --- кампании и потоки ---

    def list_campaigns(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return self._request("GET", "/campaigns", params={"limit": limit, "offset": offset})

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def delete_campaign(self, campaign_id: int) -> None:
        """Отправляет кампанию в архив Keitaro."""
        self._request("DELETE", f"/campaigns/{campaign_id}")

    def get_streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        """PUT меняет только переданные поля потока."""
        return self._request("PUT", f"/streams/{stream_id}", json=payload)

    # --- внутреннее ---

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise KeitaroError(f"Нет связи с Keitaro: {error}") from error

        if response.status_code in (401, 403):
            raise KeitaroError(
                f"Keitaro отклонил ключ API ({response.status_code}): {response.text[:200]}. "
                "Проверьте KEITARO_API_KEY в .env: ключ скопирован целиком, без кавычек и пробелов, "
                "создан в этом же аккаунте и не удалён"
            )
        if response.status_code >= 400:
            raise KeitaroError(f"Keitaro вернул {response.status_code}: {response.text[:300]}")

        return response.json() if response.content else None
