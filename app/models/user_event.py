# app/models/user_event.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
import enum

from sqlalchemy import ForeignKey, Index, String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db

if TYPE_CHECKING:
    from .user_event_option import UserEventOption
    from .event import Event


class BookingStatus(enum.Enum):
    # Werte bleiben KLEIN geschrieben – so wie in der Migration / DB
    PENDING = "pending"
    PAID = "paid"
    CANCELED = "canceled"
    REFUNDED = "refunded"
    FAILED = "failed"


def _booking_status_values(enum_cls: type[BookingStatus]) -> list[str]:
    """Sagt SQLAlchemy, welche Strings in der DB erlaubt sind."""
    return [e.value for e in enum_cls]


class UserEvent(db.Model):
    __tablename__ = "user_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Stripe
    stripe_payment_intent_id = mapped_column(String, nullable=True)
    amount_paid = mapped_column(db.Integer, nullable=True)  # in Rappen
    currency = mapped_column(String(3), default="chf")

    # 🧾 Status als DB-Enum, aber mit den KLEINEN Werten aus BookingStatus.value
    status = mapped_column(
        SAEnum(
            BookingStatus,
            name="booking_status_enum",
            values_callable=_booking_status_values,  # 👈 WICHTIG
        ),
        nullable=False,
        default=BookingStatus.PENDING,
    )

    paid_at = mapped_column(db.DateTime, nullable=True)

    # Beziehungen
    event: Mapped["Event"] = relationship("Event", backref="user_events")

    options: Mapped[list["UserEventOption"]] = relationship(
        "UserEventOption",
        back_populates="user_event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_user_event", "user_id", "event_id", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<UserEvent id={self.id} "
            f"status={self.status.value} "
            f"user={self.user_id} event={self.event_id}>"
        )
