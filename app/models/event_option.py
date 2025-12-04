# app/models/event_option.py
from __future__ import annotations

from typing import List, TYPE_CHECKING

from app.extensions import db
from sqlalchemy import ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .event import Event
    from .user_event_option import UserEventOption


EventOptionType = Enum(
    "TRAVEL",
    "TICKET",
    "CLUB_FEE",
    name="event_option_type",
)


class EventOption(db.Model):
    __tablename__ = "event_option"

    id: Mapped[int] = mapped_column(primary_key=True)

    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(EventOptionType, nullable=False)
    label: Mapped[str] = mapped_column(db.String(200), nullable=False)

    # Preis in Rappen (z.B. 5000 = 50.00 CHF)
    price_cents: Mapped[int] = mapped_column(db.Integer, nullable=False)

    # CLUB_FEE: is_required=True, is_selectable=False
    is_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_selectable: Mapped[bool] = mapped_column(default=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(db.Integer, default=0, nullable=False)

    # Beziehungen
    event: Mapped["Event"] = relationship(
        "Event",
        back_populates="options",
    )

    user_options: Mapped[List["UserEventOption"]] = relationship(
        "UserEventOption",
        back_populates="event_option",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "type",
            name="uix_event_option_event_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<EventOption id={self.id} event={self.event_id} "
            f"type={self.type} price_cents={self.price_cents}>"
        )
