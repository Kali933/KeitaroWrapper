"""Модели базы данных.

Keitaro хранит «настоящее» состояние потоков. У нас в БД лежит ЧЕРНОВИК: то, что
пользователь уже изменил в таблице, но ещё не отправил кнопкой PUSH TO KT.
Поля synced_* — снимок того, что сейчас в Keitaro. По ним определяем изменения
и откатываем их кнопкой CANCEL.
"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ACTIVE = "active"
REMOVED = "removed"


class Base(DeclarativeBase):
    pass


class CachedOffer(Base):
    """Локальная копия списка офферов Keitaro (в API нет поиска по офферам)."""

    __tablename__ = "offers_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # ID оффера в Keitaro
    name: Mapped[str]


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    kt_id: Mapped[int] = mapped_column(unique=True)  # ID кампании в Keitaro
    name: Mapped[str]

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Stream.position"
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    kt_id: Mapped[int] = mapped_column(unique=True)  # ID потока в Keitaro
    name: Mapped[str]
    schema: Mapped[str]  # landings (офферы) / redirect / action
    position: Mapped[int]
    destination: Mapped[str | None]  # куда ведёт редирект, если schema == redirect

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.position"
    )

    @property
    def has_offers(self) -> bool:
        return self.schema == "landings"

    @property
    def is_dirty(self) -> bool:
        return any(offer.is_dirty for offer in self.offers)


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"))
    offer_id: Mapped[int]
    offer_name: Mapped[str]
    position: Mapped[int]  # порядок строк в таблице

    # Текущее (черновое) состояние
    share: Mapped[int] = mapped_column(default=0)
    pinned: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(default=ACTIVE)
    is_new: Mapped[bool] = mapped_column(default=False)  # добавлен у нас, в Keitaro ещё нет

    # Снимок состояния в Keitaro
    synced_share: Mapped[int] = mapped_column(default=0)
    synced_pinned: Mapped[bool] = mapped_column(default=False)
    synced_status: Mapped[str] = mapped_column(default=ACTIVE)

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def is_dirty(self) -> bool:
        return (
            self.is_new
            or self.share != self.synced_share
            or self.pinned != self.synced_pinned
            or self.status != self.synced_status
        )


class CreatedCampaign(Base):
    """Журнал кампаний, созданных через «создатель»."""

    __tablename__ = "created_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    kt_id: Mapped[int]
    name: Mapped[str]
    alias: Mapped[str]
    geos: Mapped[str]
    offer_id: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
