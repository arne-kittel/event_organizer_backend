from app.extensions import db
import enum
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional

class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"

class User(db.Model):
    __tablename__ = "user"

    id:             Mapped[int] = mapped_column(primary_key=True)
    email:          Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash:  Mapped[Optional[str]] = mapped_column(String(256))
    role:           Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False)
