from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agent.models.enums import ActionStatus, GoalStatus


class GoalCreate(BaseModel):
    raw_input_text: str = Field(min_length=1)
    domain: str = "general"
    auto_plan: bool = False


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    raw_input_text: str
    extracted_goal: str | None
    deadline: datetime | None
    constraints: dict[str, object]
    status: GoalStatus
    domain: str
    created_at: datetime


class ScheduledActionRead(BaseModel):
    id: int
    task_id: int
    scheduled_at: datetime
    local_time: str
    duration_minutes: int
    status: ActionStatus
    attempt_number: int


class SchedulingFailureRead(BaseModel):
    unscheduled: list[str]
    reason: str


class ScheduleRead(BaseModel):
    goal_id: int
    actions: list[ScheduledActionRead]
    failure: SchedulingFailureRead | None


class PlanResponse(BaseModel):
    goal_id: int
    status: str
    clarifying_question: str | None
    schedule: ScheduleRead | None
