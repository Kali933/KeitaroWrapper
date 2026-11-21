"""Создатель кампаний: кампания + два потока (страна -> Google, остальные -> оффер)."""

import re
import secrets
import string

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError, KeitaroError
from app.keitaro_client import KeitaroClient
from app.models import CreatedCampaign
from app.services import editor, offers

GEO_PATTERN = re.compile(r"^[A-Z]{2}$")
ALIAS_ALPHABET = string.ascii_letters + string.digits


def parse_geos(raw: str) -> list[str]:
    """'mx, au,RO' -> ['MX', 'AU', 'RO'] (без дублей, только двухбуквенные коды)."""
    geos = []
    for part in raw.replace(";", ",").split(","):
        code = part.strip().upper()
        if not code:
            continue
        if not GEO_PATTERN.match(code):
            raise AppError(f"Некорректный гео-код «{part.strip()}»: нужны две буквы, например MX, AU, RO")
        if code not in geos:
            geos.append(code)
    if not geos:
        raise AppError("Укажите хотя бы один гео-код, например MX,AU,RO")
    return geos


def create_campaign(
    db: Session, client: KeitaroClient, settings: Settings, name: str, geo: str, offer_id: int
) -> dict:
    name = name.strip()
    if not name:
        raise AppError("Укажите название кампании")
    editor.check_name_prefix(name, settings.campaign_name_prefix)
    geos = parse_geos(geo)
    offer = offers.get_offer(db, client, offer_id)

    domain = _find_domain(client, settings.default_domain)
    group = _find_by_name(client.list_groups("campaigns"), settings.default_group, "Группа")
    source = _find_by_name(client.list_traffic_sources(), settings.default_source, "Источник")

    alias = "".join(secrets.choice(ALIAS_ALPHABET) for _ in range(6))
    campaign = client.create_campaign(
        {
            "name": name,
            "alias": alias,
            "type": "position",
            "domain_id": domain["id"],
            "group_id": str(group["id"]),  # в схеме Keitaro group_id — строка
            "traffic_source_id": source["id"],
        }
    )

    try:
        _create_streams(client, settings, campaign["id"], geos, offer.id)
    except KeitaroError as error:
        # Не оставляем недособранную кампанию: отправляем её в архив
        try:
            client.delete_campaign(campaign["id"])
            note = "Кампания отправлена в архив."
        except KeitaroError:
            note = f"Кампанию {campaign['id']} нужно удалить вручную."
        raise KeitaroError(f"Не удалось создать потоки: {error.message} {note}") from error

    db.add(CreatedCampaign(kt_id=campaign["id"], name=name, alias=alias, geos=",".join(geos), offer_id=offer.id))
    db.commit()

    return {
        "kt_id": campaign["id"],
        "name": name,
        "alias": alias,
        "url": f"https://{domain['name']}/{alias}",
        "view_url": f"{settings.keitaro_url.rstrip('/')}/admin/#!/campaigns/{campaign['id']}",
        "geos": geos,
        "offer": {"id": offer.id, "name": offer.name},
    }


def _create_streams(client: KeitaroClient, settings: Settings, campaign_id: int, geos: list[str], offer_id: int):
    # Поток 1: все из указанных стран -> Google
    client.create_stream(
        {
            "campaign_id": campaign_id,
            "type": "regular",
            "name": f"{', '.join(geos)} -> Google",
            "position": 1,
            "schema": "redirect",
            "action_type": "http",
            "action_payload": settings.redirect_url,
            "collect_clicks": True,
            "filters": [{"name": "country", "mode": "accept", "payload": geos}],
        }
    )
    # Поток 2: все остальные -> выбранный оффер (100% трафика)
    client.create_stream(
        {
            "campaign_id": campaign_id,
            "type": "regular",
            "name": "Offers",
            "position": 2,
            "schema": "landings",
            "action_type": "http",
            "collect_clicks": True,
            "offer_selection": "before_click",
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        }
    )


def _find_domain(client: KeitaroClient, wanted: str) -> dict:
    if not wanted:
        raise AppError("В .env не задан DEFAULT_DOMAIN")
    return _find_by_name(client.list_domains(), _bare_domain(wanted), "Домен", key=_bare_domain)


def _find_by_name(items: list[dict], wanted: str, label: str, key=lambda value: value.strip().casefold()) -> dict:
    if not wanted:
        raise AppError(f"В .env не задано значение для «{label}»")
    for item in items:
        if key(item["name"]) == key(wanted):
            return item
    raise AppError(f"{label} «{wanted}» не найден в Keitaro")


def _bare_domain(value: str) -> str:
    """'https://Example.com/' -> 'example.com'"""
    return re.sub(r"^https?://", "", value.strip().casefold()).rstrip("/")
