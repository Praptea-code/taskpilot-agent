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
