import pytest

from app.errors import AppError, ConflictError, KeitaroError, NotFoundError
from app.services import editor
from tests.conftest import CAMPAIGN, OFFERS_STREAM


def rows(campaign, stream_id=OFFERS_STREAM):
    stream = next(s for s in campaign.streams if s.kt_id == stream_id)
    return [(r.offer_id, r.share, r.status) for r in sorted(stream.offers, key=lambda r: r.position)]


@pytest.fixture
def fetched(db, keitaro):
    return editor.fetch_campaign(db, keitaro, CAMPAIGN)


def test_fetch_reads_real_structure(fetched):
    assert fetched.name == "test_repin_campaign1"
    assert [s.name for s in fetched.streams] == ["AU -> Google", "Offers"]
    google, offers = fetched.streams
    assert google.destination == "https://google.com" and not google.has_offers
    assert offers.has_offers and offers.offers[0].offer_name == "Flexacil [JOINT-PE]"
    assert rows(fetched) == [(18813, 100, "active")]
    assert not offers.is_dirty


def test_add_offers_rebalances_and_marks_dirty(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    campaign = editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    assert rows(campaign) == [(18813, 34, "active"), (11111, 33, "active"), (11112, 33, "active")]
    assert campaign.streams[1].is_dirty
    assert keitaro.calls_named("update_stream") == []  # до PUSH в Keitaro ничего не уходит


def test_add_duplicate_and_unknown_offer(db, keitaro, fetched):
    with pytest.raises(ConflictError):
        editor.add_offer(db, keitaro, OFFERS_STREAM, 18813)
    with pytest.raises(NotFoundError):
        editor.add_offer(db, keitaro, OFFERS_STREAM, 99999)


def test_cannot_add_offer_to_redirect_stream(db, keitaro, fetched):
    with pytest.raises(AppError):
        editor.add_offer(db, keitaro, 1330994, 11111)


def test_push_sends_only_active_offers_and_clears_dirty(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    campaign = editor.push(db, keitaro, OFFERS_STREAM)
    assert keitaro.kt_offers(OFFERS_STREAM) == [(18813, 50), (11111, 50)]
    assert not campaign.streams[1].is_dirty


def test_remove_goes_grey_last_and_is_not_pushed(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    editor.push(db, keitaro, OFFERS_STREAM)

    campaign = editor.remove_offer(db, OFFERS_STREAM, 18813)
    assert rows(campaign) == [(18813, 0, "removed"), (11111, 50, "active"), (11112, 50, "active")]
    campaign = editor.push(db, keitaro, OFFERS_STREAM)

    assert keitaro.kt_offers(OFFERS_STREAM) == [(11111, 50), (11112, 50)]  # в Keitaro его нет
    assert (18813, 0, "removed") in rows(campaign)                          # а у нас остаётся серым
    assert not campaign.streams[1].is_dirty


def test_remove_only_offer_and_bring_it_back_in_keitaro(db, keitaro, fetched):
    campaign = editor.remove_offer(db, OFFERS_STREAM, 18813)
    assert rows(campaign) == [(18813, 0, "removed")]
    editor.push(db, keitaro, OFFERS_STREAM)
    assert keitaro.kt_offers(OFFERS_STREAM) == []                      # поток остался без офферов

    campaign = editor.restore_offer(db, OFFERS_STREAM, 18813)
    assert rows(campaign) == [(18813, 100, "active")]
    editor.push(db, keitaro, OFFERS_STREAM)
    assert keitaro.kt_offers(OFFERS_STREAM) == [(18813, 100)]          # оффер вернулся
    assert not campaign.streams[1].is_dirty


def test_push_is_not_marked_saved_if_keitaro_ignored_it(db, keitaro, fetched):
    keitaro.ignore_updates = True
    editor.remove_offer(db, OFFERS_STREAM, 18813)
    with pytest.raises(KeitaroError, match="не совпал"):
        editor.push(db, keitaro, OFFERS_STREAM)
    stream = next(s for s in fetched.streams if s.kt_id == OFFERS_STREAM)
    assert stream.is_dirty                      # таблица по-прежнему «несохранённая»


def test_bring_back_returns_offer_to_keitaro(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.push(db, keitaro, OFFERS_STREAM)
    editor.remove_offer(db, OFFERS_STREAM, 11111)
    editor.push(db, keitaro, OFFERS_STREAM)

    campaign = editor.restore_offer(db, OFFERS_STREAM, 11111)
    assert campaign.streams[1].is_dirty
    editor.push(db, keitaro, OFFERS_STREAM)
    assert keitaro.kt_offers(OFFERS_STREAM) == [(18813, 50), (11111, 50)]


def test_cancel_restores_last_synced_state(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.push(db, keitaro, OFFERS_STREAM)
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    editor.remove_offer(db, OFFERS_STREAM, 18813)

    campaign = editor.cancel(db, OFFERS_STREAM)
    assert rows(campaign) == [(18813, 50, "active"), (11111, 50, "active")]
    assert not campaign.streams[1].is_dirty


def test_removing_unpushed_offer_just_drops_it(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    campaign = editor.remove_offer(db, OFFERS_STREAM, 11111)
    assert rows(campaign) == [(18813, 100, "active")]
    assert not campaign.streams[1].is_dirty


def test_pinned_share_is_kept_and_pushed(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.pin_offer(db, OFFERS_STREAM, 18813, 60)
    campaign = editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    assert rows(campaign) == [(18813, 60, "active"), (11111, 20, "active"), (11112, 20, "active")]

    editor.push(db, keitaro, OFFERS_STREAM)
    assert keitaro.kt_offers(OFFERS_STREAM) == [(18813, 60), (11111, 20), (11112, 20)]


def test_pin_errors_are_user_friendly(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    editor.pin_offer(db, OFFERS_STREAM, 18813, 70)
    with pytest.raises(AppError):
        editor.pin_offer(db, OFFERS_STREAM, 11111, 50)  # 70 + 50 > 100


def test_unpin_redistributes(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.pin_offer(db, OFFERS_STREAM, 18813, 80)
    campaign = editor.unpin_offer(db, OFFERS_STREAM, 18813)
    assert rows(campaign) == [(18813, 50, "active"), (11111, 50, "active")]


def test_push_is_blocked_if_all_pinned_and_sum_is_not_100(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.pin_offer(db, OFFERS_STREAM, 18813, 30)
    editor.pin_offer(db, OFFERS_STREAM, 11111, 30)
    with pytest.raises(AppError):
        editor.push(db, keitaro, OFFERS_STREAM)
    assert keitaro.calls_named("update_stream") == []


def test_fetch_after_removing_offers_directly_in_keitaro(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    editor.push(db, keitaro, OFFERS_STREAM)

    # кто-то убрал два оффера прямо в Keitaro (оставшийся имеет долю 34 из 100)
    keitaro.streams[CAMPAIGN][1]["offers"] = [{"offer_id": 18813, "state": "active", "share": 34}]

    campaign = editor.fetch_campaign(db, keitaro, CAMPAIGN)
    assert rows(campaign) == [(18813, 100, "active"), (11111, 0, "removed"), (11112, 0, "removed")]
    # доли нормализованы до 100, таблица подсвечена как несохранённая
    assert campaign.streams[1].is_dirty


def test_fetch_discards_unpushed_draft(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    campaign = editor.fetch_campaign(db, keitaro, CAMPAIGN)
    assert rows(campaign) == [(18813, 100, "active")]
    assert not campaign.streams[1].is_dirty


def test_fetch_keeps_pins_and_removed_rows(db, keitaro, fetched):
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11111)
    editor.pin_offer(db, OFFERS_STREAM, 18813, 70)
    editor.push(db, keitaro, OFFERS_STREAM)
    editor.add_offer(db, keitaro, OFFERS_STREAM, 11112)
    editor.remove_offer(db, OFFERS_STREAM, 11112)  # непушенный оффер просто исчезает
    campaign = editor.fetch_campaign(db, keitaro, CAMPAIGN)
    stream = campaign.streams[1]
    assert next(r for r in stream.offers if r.offer_id == 18813).pinned is True
    assert rows(campaign) == [(18813, 70, "active"), (11111, 30, "active")]
