"""Пересчёт долей (весов) офферов в потоке.

Чистые функции без базы данных и сети: так логику легко читать и тестировать.

Правила:
- доли целые (Keitaro принимает share как integer), сумма активных = 100;
- закреплённый (pinned) оффер сохраняет свою долю;
- остаток (100 - сумма закреплённых) делится поровну между незакреплёнными,
  лишние проценты достаются первым по порядку (3 оффера -> 34 / 33 / 33);
- удалённый (removed) оффер имеет долю 0 и в пересчёте не участвует.
"""

from dataclasses import dataclass

ACTIVE = "active"
REMOVED = "removed"
TOTAL_SHARE = 100


class WeightsError(ValueError):
    """Нельзя распределить доли с текущими настройками."""


@dataclass
class OfferRow:
    offer_id: int
    status: str = ACTIVE
    pinned: bool = False
    share: int = 0


def recalculate(rows: list[OfferRow]) -> None:
    """Пересчитывает share у всех строк (изменяет объекты на месте)."""
    for row in rows:
        if row.status == REMOVED:
            row.share = 0
            row.pinned = False  # удалённый оффер не может быть закреплён

    active = [row for row in rows if row.status == ACTIVE]
    pinned = [row for row in active if row.pinned]
    free = [row for row in active if not row.pinned]

    pinned_sum = sum(row.share for row in pinned)
    if pinned_sum > TOTAL_SHARE:
        raise WeightsError(f"Сумма закреплённых долей {pinned_sum}% больше {TOTAL_SHARE}%")

    if not free:
        return  # делить не между кем; корректность суммы проверяет validate_for_push

    base, extra = divmod(TOTAL_SHARE - pinned_sum, len(free))
    for index, row in enumerate(free):
        row.share = base + (1 if index < extra else 0)


def pin(rows: list[OfferRow], offer_id: int, share: int) -> None:
    """Закрепляет долю оффера и пересчитывает остальных."""
    if not 0 <= share <= TOTAL_SHARE:
        raise WeightsError("Доля должна быть от 0 до 100")
    row = _find_active(rows, offer_id)
    row.pinned = True
    row.share = share
    recalculate(rows)


def unpin(rows: list[OfferRow], offer_id: int) -> None:
    """Снимает закрепление и пересчитывает доли."""
    _find_active(rows, offer_id).pinned = False
    recalculate(rows)


def sort_rows(rows: list[OfferRow]) -> list[OfferRow]:
    """Активные офферы сверху, удалённые в конце (порядок внутри групп сохраняется)."""
    return [r for r in rows if r.status == ACTIVE] + [r for r in rows if r.status == REMOVED]


def validate_for_push(rows: list[OfferRow]) -> None:
    """Проверяет, что таблицу можно отправлять в Keitaro.

    Поток вообще без офферов допустим (в Keitaro такие потоки бывают); если же офферы есть,
    их доли должны давать ровно 100%.
    """
    active = [row for row in rows if row.status == ACTIVE]
    if not active:
        return
    total = sum(row.share for row in active)
    if total != TOTAL_SHARE:
        raise WeightsError(f"Сумма долей {total}%, должна быть {TOTAL_SHARE}%")


def _find_active(rows: list[OfferRow], offer_id: int) -> OfferRow:
    for row in rows:
        if row.offer_id == offer_id and row.status == ACTIVE:
            return row
    raise WeightsError(f"Активный оффер {offer_id} не найден")
