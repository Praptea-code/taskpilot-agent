from typing import Literal

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    user_id: int = Field(gt=0)
    text: str = Field(min_length=1)
    channel: Literal["text", "voice"] = "text"


class InboundResultRead(BaseModel):
    kind: str
    message: str
    session_id: int | None = None
    goal_id: int | None = None
    status: str | None = None
    action: str | None = None
