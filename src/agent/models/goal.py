from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.models.base import Base, TimestampMixin
from agent.models.enums import GoalStatus, enum_column

if TYPE_CHECKING:
    from agent.models.task import Task
    from agent.models.user import User


class Goal(TimestampMixin, Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    raw_input_text: Mapped[str] = mapped_column(Text)
    extracted_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    constraints: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    status: Mapped[GoalStatus] = mapped_column(enum_column(GoalStatus), default=GoalStatus.PENDING)
    domain: Mapped[str] = mapped_column(String(64), default="general")

    user: Mapped["User"] = relationship(back_populates="goals")
    tasks: Mapped[list["Task"]] = relationship(back_populates="goal")
