# app/models/user_event_option.py
from __future__ import annotations

from typing import TYPE_CHECKING

from app.extensions import db
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .user_event import UserEvent
    from .event_option import EventOption


class UserEventOption(db.Model):
    __tablename__ = "user_event_option"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_event_id: Mapped[int] = mapped_column(
        ForeignKey("user_event.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_option_id: Mapped[int] = mapped_column(
        ForeignKey("event_option.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Preis-Snapshot beim Buchen (in Rappen)
    price_cents: Mapped[int] = mapped_column(db.Integer, nullable=False)

    user_event: Mapped["UserEvent"] = relationship(
        "UserEvent",
        back_populates="options",
    )

    event_option: Mapped["EventOption"] = relationship(
        "EventOption",
        back_populates="user_options",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_event_id",
            "event_option_id",
            name="uix_user_event_option_user_event_option",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserEventOption user_event={self.user_event_id} "
            f"option={self.event_option_id} price_cents={self.price_cents}>"
        )
