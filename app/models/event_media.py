# app/models/event_media.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
import enum

if TYPE_CHECKING:
    # Nur für Typprüfung – verhindert Laufzeit-Zirkelimporte
    from .event import Event

class MediaType(str, enum.Enum):
    image = "image"
    video = "video"
    audio = "audio"
    document = "document"


class EventMedia(db.Model):
    __tablename__ = "event_media"

    id:             Mapped[int] = mapped_column(primary_key=True)
    event_id:       Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True)

    type:           Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False)
    mime:           Mapped[str] = mapped_column(db.String(100), nullable=False)
    blob_name:      Mapped[str] = mapped_column(db.String(500), nullable=False)

    poster_blob:    Mapped[Optional[str]] = mapped_column(db.String(500))
    variants_json:  Mapped[Optional[dict]] = mapped_column(db.JSON)

    size_bytes:     Mapped[Optional[int]]
    width:          Mapped[Optional[int]]
    height:         Mapped[Optional[int]]
    duration_secs:  Mapped[Optional[float]]

    sort_order:     Mapped[Optional[int]]
    created_at:     Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    # Rückbeziehung zum Event (passend zu Event.media back_populates)
    event: Mapped["Event"] = relationship("Event", back_populates="media_items")

    def __repr__(self) -> str:  # optional, hilfreich beim Debugging
        return f"<EventMedia id={self.id} event_id={self.event_id} kind={self.media_kind} name={self.blob_name!r}>"
