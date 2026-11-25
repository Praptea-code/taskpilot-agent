from typing import TYPE_CHECKING

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from agent.models.goal import Goal


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    notification_prefs: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    escalation_policy: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key_salt: Mapped[str | None] = mapped_column(String(64), nullable=True)

    goals: Mapped[list["Goal"]] = relationship(back_populates="user")
