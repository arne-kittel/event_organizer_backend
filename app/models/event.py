# app/models/event.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from app.extensions import db
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .event_media import EventMedia
from .event_option import EventOption


class Event(db.Model):
    __tablename__ = "event"

    id:                 Mapped[int] = mapped_column(primary_key=True)
    title:              Mapped[str] = mapped_column(db.String(200), nullable=False)
    description:        Mapped[Optional[str]] = mapped_column(db.Text)
    creator_id:         Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    host_id:            Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    location:           Mapped[str] = mapped_column(db.String(200))
    is_online:          Mapped[bool] = mapped_column(default=False)
    start_time:         Mapped[datetime] = mapped_column()
    end_time:           Mapped[Optional[datetime]] = mapped_column()
    max_participants:   Mapped[Optional[int]] = mapped_column()

    media_items: Mapped[List["EventMedia"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventMedia.sort_order.asc(), EventMedia.created_at.asc()",
    )

    # 💰 Preis-Optionen (Travel, Ticket, Club Fee, etc.)
    options: Mapped[List["EventOption"]] = relationship(
        "EventOption",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventOption.sort_order.asc(), EventOption.id.asc()",
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r}>"
