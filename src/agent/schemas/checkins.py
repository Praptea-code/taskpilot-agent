from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CheckInCreate(BaseModel):
    scheduled_action_id: int
    response_text: str = Field(min_length=1)


class CheckInRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    scheduled_action_id: int
    occurred_at: datetime
    user_response_text: str | None
    outcome: str | None
