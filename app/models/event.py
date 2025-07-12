from app.extensions import db
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import List, Optional

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
