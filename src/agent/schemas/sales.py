from pydantic import BaseModel, Field


class SendEmailPayload(BaseModel):
    lead_id: int = Field(gt=0)
    template: str = Field(min_length=1)
    step: int = Field(default=1, ge=1)
