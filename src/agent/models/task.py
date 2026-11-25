from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.models.base import Base
from agent.models.enums import TaskStatus, enum_column

if TYPE_CHECKING:
    from agent.models.goal import Goal
    from agent.models.scheduled_action import ScheduledAction


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    estimated_effort_minutes: Mapped[int] = mapped_column(Integer, default=30)
    action_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[TaskStatus] = mapped_column(enum_column(TaskStatus), default=TaskStatus.PENDING)
    miss_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)

    goal: Mapped["Goal"] = relationship(back_populates="tasks")
    scheduled_actions: Mapped[list["ScheduledAction"]] = relationship(back_populates="task")
