from datetime import datetime

from pydantic import BaseModel, Field


class SessionReplyCreate(BaseModel):
    text: str = Field(min_length=1)


class SessionReplyRead(BaseModel):
    session_id: int
    action: str
    message_to_user: str
    applied_time: datetime | None
    status: str
