"""Офферы Keitaro: локальный кэш и поиск (в API Keitaro поиска по офферам нет)."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.keitaro_client import KeitaroClient
from app.models import CachedOffer


def refresh_offers(db: Session, client: KeitaroClient) -> int:
    """Полностью обновляет кэш офферов из Keitaro. Возвращает их количество."""
    offers = [o for o in client.list_offers() if o.get("state") != "deleted"]
    db.execute(delete(CachedOffer))
    db.add_all(CachedOffer(id=o["id"], name=o["name"]) for o in offers)
    db.commit()
    return len(offers)


def search_offers(db: Session, client: KeitaroClient, query: str, limit: int = 20) -> list[CachedOffer]:
    """Поиск по ID или части названия (для автокомплита)."""
    if db.scalar(select(CachedOffer.id).limit(1)) is None:
        refresh_offers(db, client)

    query = query.strip().casefold()
    result = []
    for offer in db.scalars(select(CachedOffer).order_by(CachedOffer.id)):
        if not query or query in str(offer.id) or query in offer.name.casefold():
            result.append(offer)
            if len(result) >= limit:
                break
    return result


def get_offer(db: Session, client: KeitaroClient, offer_id: int) -> CachedOffer:
    """Находит оффер по ID. Если его нет в кэше, один раз обновляет кэш."""
    offer = db.get(CachedOffer, offer_id)
    if offer is None:
        refresh_offers(db, client)
        offer = db.get(CachedOffer, offer_id)
    if offer is None:
        raise NotFoundError(f"Оффер {offer_id} не найден в Keitaro")
    return offer


def get_names(db: Session, client: KeitaroClient, offer_ids: list[int]) -> dict[int, str]:
    """Названия офферов по ID; для неизвестных подставляется заглушка."""
    if any(db.get(CachedOffer, offer_id) is None for offer_id in offer_ids):
        refresh_offers(db, client)
    names = {}
    for offer_id in offer_ids:
        offer = db.get(CachedOffer, offer_id)
        names[offer_id] = offer.name if offer else f"Offer #{offer_id}"
    return names
