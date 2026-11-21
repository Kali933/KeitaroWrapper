import pytest

from app.services.weights import (
    ACTIVE, REMOVED, OfferRow, WeightsError,
    pin, recalculate, sort_rows, unpin, validate_for_push,
)


def shares(rows):
    return [row.share for row in rows]


def make(*ids):
    return [OfferRow(offer_id=i) for i in ids]


def test_single_offer_gets_100():
    rows = make(1)
    recalculate(rows)
    assert shares(rows) == [100]


def test_three_offers_34_33_33_as_in_demo():
    rows = make(1, 2, 3)
    recalculate(rows)
    assert shares(rows) == [34, 33, 33]


def test_four_offers_25_each():
    rows = make(1, 2, 3, 4)
    recalculate(rows)
    assert shares(rows) == [25, 25, 25, 25]


def test_removed_offer_gets_zero_and_others_rebalance():
    rows = make(1, 2, 3, 4)
    recalculate(rows)
    rows[1].status = REMOVED
    recalculate(rows)
    assert shares(rows) == [34, 0, 33, 33]


def test_bring_back_restores_distribution():
    rows = make(1, 2, 3)
    rows[1].status = REMOVED
    recalculate(rows)
    rows[1].status = ACTIVE
    recalculate(rows)
    assert shares(rows) == [34, 33, 33]


def test_pinned_share_is_kept_when_adding_offers():
    rows = make(1, 2)
    recalculate(rows)
    pin(rows, 1, 60)
    assert shares(rows) == [60, 40]
    rows.append(OfferRow(offer_id=3))
    recalculate(rows)
    assert shares(rows) == [60, 20, 20]


def test_pinned_with_odd_remainder():
    rows = make(1, 2, 3)
    pin(rows, 1, 50)
    assert shares(rows) == [50, 25, 25]
    rows.append(OfferRow(offer_id=4))
    recalculate(rows)
    assert shares(rows) == [50, 17, 17, 16]


def test_unpin_redistributes_evenly():
    rows = make(1, 2)
    pin(rows, 1, 70)
    unpin(rows, 1)
    assert shares(rows) == [50, 50]


def test_pinned_sum_over_100_is_error():
    rows = make(1, 2, 3)
    pin(rows, 1, 70)
    with pytest.raises(WeightsError):
        pin(rows, 2, 50)


def test_pin_out_of_range_is_error():
    rows = make(1)
    with pytest.raises(WeightsError):
        pin(rows, 1, 101)


def test_pin_removed_offer_is_error():
    rows = make(1, 2)
    rows[0].status = REMOVED
    with pytest.raises(WeightsError):
        pin(rows, 1, 10)


def test_all_pinned_not_summing_to_100_fails_validation():
    rows = make(1, 2)
    pin(rows, 1, 30)
    pin(rows, 2, 30)  # free-офферов нет, остаток не распределить
    with pytest.raises(WeightsError):
        validate_for_push(rows)


def test_pinned_100_gives_zero_to_others_and_is_valid():
    rows = make(1, 2)
    pin(rows, 1, 100)
    assert shares(rows) == [100, 0]
    validate_for_push(rows)


def test_stream_without_offers_is_allowed():
    rows = make(1)
    rows[0].status = REMOVED
    recalculate(rows)
    validate_for_push(rows)  # поток без офферов допустим, ошибки нет


def test_sort_puts_removed_last_keeping_order():
    rows = make(1, 2, 3, 4)
    rows[0].status = REMOVED
    rows[2].status = REMOVED
    assert [r.offer_id for r in sort_rows(rows)] == [2, 4, 1, 3]


@pytest.mark.parametrize("count", range(1, 13))
def test_sum_is_always_100(count):
    rows = make(*range(count))
    recalculate(rows)
    assert sum(shares(rows)) == 100
