"""HTTP-эндпоинты: создатель кампаний, поиск офферов, редактор потоков."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_db
from app.keitaro_client import KeitaroClient
from app.routers.deps import get_client, settings_dep
from app.schemas import CampaignCreate, OfferAdd, PinRequest, campaign_state
from app.services import campaign_creator, editor, offers

router = APIRouter(prefix="/api")


@router.get("/info")
def info(settings: Settings = Depends(settings_dep)):
    """К какому Keitaro подключено приложение (показывается в шапке интерфейса)."""
    key = settings.keitaro_api_key
    return {
        "keitaro_url": settings.keitaro_url,
        "campaign_prefix": settings.campaign_name_prefix,
        # ключ целиком не показываем: достаточно последних 4 символов и длины, чтобы сверить с .env
        "api_key": f"…{key[-4:]} ({len(key)} симв.)" if key else "не задан",
    }


# --- офферы ---

@router.get("/offers")
def search_offers(
    q: str = "",
    limit: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
):
    """Автокомплит: поиск по ID или названию (с limit=1000 получим все офферы)."""
    return [{"id": o.id, "name": o.name} for o in offers.search_offers(db, client, q, limit)]


@router.post("/offers/refresh")
def refresh_offers(db: Session = Depends(get_db), client: KeitaroClient = Depends(get_client)):
    return {"count": offers.refresh_offers(db, client)}


# --- создатель кампаний ---

@router.post("/campaigns")
def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
    settings: Settings = Depends(settings_dep),
):
    return campaign_creator.create_campaign(db, client, settings, body.name, body.geo, body.offer_id)


@router.get("/campaigns/remote")
def list_remote_campaigns(
    q: str = "", client: KeitaroClient = Depends(get_client), settings: Settings = Depends(settings_dep)
):
    """Список кампаний для выбора в редакторе: только с нашим префиксом, с фильтром по названию."""
    campaigns = client.list_campaigns(limit=200)
    q = q.strip().casefold()
    return [
        {"id": c["id"], "name": c["name"]}
        for c in campaigns
        if c["name"].startswith(settings.campaign_name_prefix)
        and (not q or q in c["name"].casefold() or q == str(c["id"]))
    ]


# --- редактор потоков ---

@router.post("/editor/{campaign_id}/fetch")
def fetch(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
    settings: Settings = Depends(settings_dep),
):
    campaign = editor.fetch_campaign(db, client, campaign_id, settings.campaign_name_prefix)
    return campaign_state(campaign, settings.keitaro_url)


@router.get("/editor/{campaign_id}")
def state(campaign_id: int, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    return campaign_state(editor.get_campaign_by_kt_id(db, campaign_id), settings.keitaro_url)


@router.post("/streams/{stream_id}/offers")
def add_offer(
    stream_id: int,
    body: OfferAdd,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
    settings: Settings = Depends(settings_dep),
):
    return campaign_state(editor.add_offer(db, client, stream_id, body.offer_id), settings.keitaro_url)


@router.delete("/streams/{stream_id}/offers/{offer_id}")
def remove_offer(stream_id: int, offer_id: int, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    return campaign_state(editor.remove_offer(db, stream_id, offer_id), settings.keitaro_url)


@router.post("/streams/{stream_id}/offers/{offer_id}/restore")
def restore_offer(stream_id: int, offer_id: int, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    return campaign_state(editor.restore_offer(db, stream_id, offer_id), settings.keitaro_url)


@router.put("/streams/{stream_id}/offers/{offer_id}/pin")
def pin_offer(
    stream_id: int, offer_id: int, body: PinRequest,
    db: Session = Depends(get_db), settings: Settings = Depends(settings_dep),
):
    return campaign_state(editor.pin_offer(db, stream_id, offer_id, body.share), settings.keitaro_url)


@router.delete("/streams/{stream_id}/offers/{offer_id}/pin")
def unpin_offer(stream_id: int, offer_id: int, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    return campaign_state(editor.unpin_offer(db, stream_id, offer_id), settings.keitaro_url)


@router.post("/streams/{stream_id}/cancel")
def cancel(stream_id: int, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    return campaign_state(editor.cancel(db, stream_id), settings.keitaro_url)


@router.post("/streams/{stream_id}/push")
def push(
    stream_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
    settings: Settings = Depends(settings_dep),
):
    campaign = editor.push(db, client, stream_id, settings.campaign_name_prefix)
    return campaign_state(campaign, settings.keitaro_url)
