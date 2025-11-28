# app/models/user_event.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from .event import Event


class UserEvent(db.Model):
    """Verknüpfungstabelle für User-Event-Registrierungen"""
    __tablename__ = 'user_event'

    id:         Mapped[int] = mapped_column(primary_key=True)
    user_id:    Mapped[str] = mapped_column(db.String(255), nullable=False, index=True)
    event_id:   Mapped[int] = mapped_column(
        ForeignKey("event.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    timestamp:  Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

     # 🧾 Stripe-Daten
    stripe_payment_intent_id = db.Column(db.String, nullable=True)
    amount_paid = db.Column(db.Integer, nullable=True)  # in Rappen (z.B. 5000 = 50.00 CHF)
    currency = db.Column(db.String(3), default="chf")

    # Optionale Rückbeziehung zum Event (falls du sie brauchst)
    # event: Mapped["Event"] = relationship("Event", back_populates="participants")

    # Unique Constraint: Ein User kann sich nur einmal für ein Event registrieren
    __table_args__ = (
        Index('idx_user_event', 'user_id', 'event_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<UserEvent id={self.id} user={self.user_id} event={self.event_id}>"