from typing import Literal

from pydantic import BaseModel, Field


class GoalConstraints(BaseModel):
    earliest_time: str | None = None
    latest_time: str | None = None
    preferred_days: list[str] = Field(default_factory=list)
    max_session_minutes: int | None = None
    notes: str | None = None


class ExtractedGoal(BaseModel):
    title: str
    deadline: str | None = None
    constraints: GoalConstraints = Field(default_factory=GoalConstraints)
    clarifying_question: str | None = None


class ExtractedTask(BaseModel):
    description: str
    estimated_effort_minutes: int
    action_type: str
    order: int


class ExtractedTasks(BaseModel):
    tasks: list[ExtractedTask]


class CheckInDecision(BaseModel):
    outcome: Literal["completed", "rescheduled", "cancelled", "unclear"]
    new_time: str | None = None
    message_to_user: str | None = None


class RenegotiationDecision(BaseModel):
    action: Literal["reschedule", "keep_as_is", "cancel", "ask_user"]
    new_time: str | None = None
    reason: str
    message_to_user: str
