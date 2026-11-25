from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CredentialCreate(BaseModel):
    service: str
    value: str


class CredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service: str
    created_at: datetime
