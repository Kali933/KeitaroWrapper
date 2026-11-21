"""Тела запросов API и сборка ответа для редактора."""

from pydantic import BaseModel, Field

from app.models import Campaign


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1)
    geo: str = Field(min_length=1, description="Гео-коды через запятую: MX,AU,RO")
    offer_id: int


class OfferAdd(BaseModel):
    offer_id: int


class PinRequest(BaseModel):
    share: int = Field(ge=0, le=100)


def campaign_state(campaign: Campaign, keitaro_url: str) -> dict:
    """Состояние кампании для фронта: потоки, строки офферов и признаки несохранённых правок."""
    return {
        "kt_id": campaign.kt_id,
        "name": campaign.name,
        "view_url": f"{keitaro_url.rstrip('/')}/admin/#!/campaigns/{campaign.kt_id}",
        "streams": [
            {
                "kt_id": stream.kt_id,
                "name": stream.name,
                "position": stream.position,
                "schema": stream.schema,
                "destination": stream.destination,
                "has_offers": stream.has_offers,
                "dirty": stream.is_dirty,
                "offers": [
                    {
                        "offer_id": row.offer_id,
                        "name": row.offer_name,
                        "share": row.share,
                        "pinned": row.pinned,
                        "status": row.status,
                        "is_new": row.is_new,
                        "dirty": row.is_dirty,
                    }
                    for row in _display_order(stream)
                ],
            }
            for stream in campaign.streams
        ],
    }


def _display_order(stream):
    rows = sorted(stream.offers, key=lambda row: row.position)
    return [r for r in rows if r.status == "active"] + [r for r in rows if r.status == "removed"]
