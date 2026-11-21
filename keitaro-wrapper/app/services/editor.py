"""Редактор офферов в потоках: черновик в БД + синхронизация с Keitaro.

Жизненный цикл:
  FETCH  -> черновик = состояние Keitaro
  ADD / REMOVE / BRING BACK / PIN -> меняется только черновик (в Keitaro ничего не уходит)
  PUSH   -> черновик отправляется в Keitaro и становится «сохранённым»
  CANCEL -> черновик возвращается к последнему «сохранённому» состоянию
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, ConflictError, ForbiddenError, KeitaroError, NotFoundError
from app.keitaro_client import KeitaroClient
from app.models import ACTIVE, REMOVED, Campaign, Stream, StreamOffer
from app.services import offers as offers_service
from app.services import weights
from app.services.weights import WeightsError


# --- FETCH: забрать состояние из Keitaro ---

def check_name_prefix(campaign_name: str, prefix: str) -> None:
    """Не даёт трогать чужие кампании: допускаются только названия с нашим префиксом."""
    if prefix and not campaign_name.startswith(prefix):
        raise ForbiddenError(
            f"Кампания «{campaign_name}» не начинается с «{prefix}». "
            "Редактировать можно только свои тестовые кампании"
        )


def fetch_campaign(db: Session, client: KeitaroClient, kt_campaign_id: int, name_prefix: str = "") -> Campaign:
    kt_campaign = client.get_campaign(kt_campaign_id)
    check_name_prefix(kt_campaign["name"], name_prefix)
    kt_streams = [s for s in client.get_streams(kt_campaign_id) if s.get("state") != "deleted"]

    campaign = db.scalar(select(Campaign).where(Campaign.kt_id == kt_campaign_id))
    if campaign is None:
        campaign = Campaign(kt_id=kt_campaign_id, name=kt_campaign["name"])
        db.add(campaign)
    campaign.name = kt_campaign["name"]

    existing = {stream.kt_id: stream for stream in campaign.streams}
    kt_ids = {s["id"] for s in kt_streams}

    for stream in list(campaign.streams):
        if stream.kt_id not in kt_ids:  # поток удалили в Keitaro
            campaign.streams.remove(stream)

    for kt_stream in sorted(kt_streams, key=lambda s: s["position"]):
        stream = existing.get(kt_stream["id"])
        if stream is None:
            stream = Stream(kt_id=kt_stream["id"])
            campaign.streams.append(stream)
        stream.name = kt_stream["name"]
        stream.schema = kt_stream["schema"]
        stream.position = kt_stream["position"]
        stream.destination = kt_stream.get("action_payload") if kt_stream["schema"] == "redirect" else None

        if stream.has_offers:
            _sync_offers(db, client, stream, kt_stream.get("offers", []))
        else:
            stream.offers.clear()

    db.commit()
    return campaign


def _sync_offers(db: Session, client: KeitaroClient, stream: Stream, kt_offers: list[dict]) -> None:
    """Приводит строки таблицы к состоянию Keitaro."""
    kt_active = {o["offer_id"]: o for o in kt_offers if o.get("state", ACTIVE) == ACTIVE}
    kt_disabled = {o["offer_id"] for o in kt_offers if o.get("state", ACTIVE) != ACTIVE}
    names = offers_service.get_names(db, client, list(kt_active) + list(kt_disabled))
    rows = {row.offer_id: row for row in stream.offers}

    for row in list(stream.offers):
        if row.is_new and row.offer_id not in kt_active:  # несохранённый черновик отбрасываем
            stream.offers.remove(row)
            del rows[row.offer_id]

    next_position = max((row.position for row in stream.offers), default=0) + 1

    for offer_id, kt_offer in kt_active.items():
        row = rows.get(offer_id)
        if row is None:
            row = StreamOffer(offer_id=offer_id, position=next_position)
            next_position += 1
            stream.offers.append(row)
        row.offer_name = names[offer_id]
        row.status = ACTIVE
        row.share = kt_offer["share"]
        row.is_new = False
        _mark_synced(row)

    for offer_id in kt_disabled | (rows.keys() - kt_active.keys()):
        row = rows.get(offer_id)
        if row is None:
            row = StreamOffer(offer_id=offer_id, offer_name=names[offer_id], position=next_position)
            next_position += 1
            stream.offers.append(row)
        # оффера нет (или он выключен) в Keitaro: показываем серым, как удалённый
        row.status = REMOVED
        row.share = 0
        row.pinned = False
        row.is_new = False
        _mark_synced(row)

    # Если после правок в самом Keitaro сумма долей не равна 100, нормализуем:
    # таблица подсветится как несохранённая, и это можно отправить кнопкой PUSH
    active = _ordered(stream, only_active=True)
    if active and sum(row.share for row in active) != weights.TOTAL_SHARE:
        try:
            weights.recalculate(_ordered(stream))
        except WeightsError:
            pass


# --- действия над черновиком ---

def add_offer(db: Session, client: KeitaroClient, stream_kt_id: int, offer_id: int) -> Campaign:
    stream = _get_stream(db, stream_kt_id)
    _require_offers_stream(stream)
    offer = offers_service.get_offer(db, client, offer_id)

    row = _find_row(stream, offer_id)
    if row is not None and row.status == ACTIVE:
        raise ConflictError("Этот оффер уже есть в потоке")

    if row is not None:  # был удалён, возвращаем
        row.status = ACTIVE
    else:
        position = max((r.position for r in stream.offers), default=0) + 1
        stream.offers.append(
            StreamOffer(
                offer_id=offer.id, offer_name=offer.name, position=position, status=ACTIVE, is_new=True,
                share=0, synced_share=0, synced_pinned=False, synced_status=REMOVED,
            )
        )
    return _recalculate_and_save(db, stream)


def remove_offer(db: Session, stream_kt_id: int, offer_id: int) -> Campaign:
    stream = _get_stream(db, stream_kt_id)
    row = _find_active_row(stream, offer_id)
    if row.is_new:  # в Keitaro его ещё не было: просто убираем из черновика
        stream.offers.remove(row)
    else:
        row.status = REMOVED
    return _recalculate_and_save(db, stream)


def restore_offer(db: Session, stream_kt_id: int, offer_id: int) -> Campaign:
    stream = _get_stream(db, stream_kt_id)
    row = _find_row(stream, offer_id)
    if row is None or row.status != REMOVED:
        raise NotFoundError("Среди удалённых нет такого оффера")
    row.status = ACTIVE
    return _recalculate_and_save(db, stream)


def pin_offer(db: Session, stream_kt_id: int, offer_id: int, share: int) -> Campaign:
    stream = _get_stream(db, stream_kt_id)
    _find_active_row(stream, offer_id)
    try:
        weights.pin(_ordered(stream), offer_id, share)
    except WeightsError as error:
        db.rollback()
        raise AppError(str(error)) from error
    db.commit()
    return stream.campaign


def unpin_offer(db: Session, stream_kt_id: int, offer_id: int) -> Campaign:
    stream = _get_stream(db, stream_kt_id)
    _find_active_row(stream, offer_id)
    weights.unpin(_ordered(stream), offer_id)
    db.commit()
    return stream.campaign


def cancel(db: Session, stream_kt_id: int) -> Campaign:
    """Отменяет все несохранённые изменения потока."""
    stream = _get_stream(db, stream_kt_id)
    for row in list(stream.offers):
        if row.is_new:
            stream.offers.remove(row)
        else:
            row.share = row.synced_share
            row.pinned = row.synced_pinned
            row.status = row.synced_status
    db.commit()
    return stream.campaign


def push(db: Session, client: KeitaroClient, stream_kt_id: int, name_prefix: str = "") -> Campaign:
    """Отправляет черновик в Keitaro. Удалённые офферы в Keitaro не попадают."""
    stream = _get_stream(db, stream_kt_id)
    _require_offers_stream(stream)
    check_name_prefix(stream.campaign.name, name_prefix)  # единственное место, где мы пишем в чужой Keitaro

    rows = _ordered(stream)
    try:
        weights.validate_for_push(rows)
    except WeightsError as error:
        raise AppError(str(error)) from error

    payload = [
        {"offer_id": row.offer_id, "share": row.share, "state": "active"}
        for row in rows
        if row.status == ACTIVE
    ]
    client.update_stream(stream.kt_id, {"offers": payload})
    _verify_pushed(client, stream, payload)

    for row in stream.offers:
        row.is_new = False
        _mark_synced(row)
    db.commit()
    return stream.campaign


# --- вспомогательное ---

def _verify_pushed(client: KeitaroClient, stream: Stream, payload: list[dict]) -> None:
    """Перечитывает поток и убеждается, что Keitaro применил именно то, что мы отправили.

    Ответ «200 OK» ещё не гарантирует, что список офферов заменён (например, пустой список
    сервер мог проигнорировать). Если состав не совпал, помечать таблицу сохранённой нельзя.
    """
    kt_stream = next((s for s in client.get_streams(stream.campaign.kt_id) if s["id"] == stream.kt_id), None)
    actual = {o["offer_id"]: o["share"] for o in (kt_stream or {}).get("offers", []) if o.get("state", ACTIVE) == ACTIVE}
    expected = {o["offer_id"]: o["share"] for o in payload}
    if actual != expected:
        raise KeitaroError(
            "Keitaro принял запрос, но состав офферов в потоке не совпал с отправленным. "
            f"В Keitaro сейчас: {actual or 'нет офферов'}. Нажмите FETCH STREAMS FROM KT и проверьте поток"
        )


def get_campaign_by_kt_id(db: Session, kt_campaign_id: int) -> Campaign:
    campaign = db.scalar(select(Campaign).where(Campaign.kt_id == kt_campaign_id))
    if campaign is None:
        raise NotFoundError("Кампания ещё не загружена: нажмите FETCH STREAMS FROM KT")
    return campaign


def _get_stream(db: Session, stream_kt_id: int) -> Stream:
    stream = db.scalar(select(Stream).where(Stream.kt_id == stream_kt_id))
    if stream is None:
        raise NotFoundError("Поток не найден: загрузите кампанию заново (FETCH)")
    return stream


def _require_offers_stream(stream: Stream) -> None:
    if not stream.has_offers:
        raise AppError("В этом потоке нет офферов (у него другая схема)")


def _find_row(stream: Stream, offer_id: int) -> StreamOffer | None:
    return next((row for row in stream.offers if row.offer_id == offer_id), None)


def _find_active_row(stream: Stream, offer_id: int) -> StreamOffer:
    row = _find_row(stream, offer_id)
    if row is None or row.status != ACTIVE:
        raise NotFoundError("Активный оффер не найден в потоке")
    return row


def _ordered(stream: Stream, only_active: bool = False) -> list[StreamOffer]:
    """Строки в порядке показа: активные по порядку добавления, затем удалённые."""
    rows = weights.sort_rows(sorted(stream.offers, key=lambda row: row.position))
    return [row for row in rows if row.status == ACTIVE] if only_active else rows


def _recalculate_and_save(db: Session, stream: Stream) -> Campaign:
    weights.recalculate(_ordered(stream))
    db.commit()
    return stream.campaign


def _mark_synced(row: StreamOffer) -> None:
    row.synced_share = row.share
    row.synced_pinned = row.pinned
    row.synced_status = row.status
