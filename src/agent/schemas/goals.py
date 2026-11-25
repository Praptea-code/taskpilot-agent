from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agent.models.enums import GoalStatus


class GoalCreate(BaseModel):
    raw_input_text: str = Field(min_length=1)
    domain: str = "general"


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
