from typing import Literal

from pydantic import BaseModel, Field


class EscalationLevel(BaseModel):
    level: int = Field(ge=1)
    channel: Literal["text", "email"] = "text"
    tone: Literal["neutral", "insistent", "urgent"] = "neutral"
    notify_contacts: list[str] = Field(default_factory=list)


DEFAULT_LEVELS = [
    EscalationLevel(level=1, channel="text", tone="insistent"),
    EscalationLevel(level=2, channel="text", tone="urgent"),
]


class EscalationPolicy(BaseModel):
    misses_before_escalate: int = Field(default=2, ge=1)
    levels: list[EscalationLevel] = Field(
        default_factory=lambda: [level.model_copy(deep=True) for level in DEFAULT_LEVELS]
    )


DEFAULT_ESCALATION_POLICY = EscalationPolicy()


class EscalationDecision(BaseModel):
    level: int = Field(ge=1)
    channel: Literal["text", "email"]
    tone: Literal["neutral", "insistent", "urgent"]
    notify_contacts: list[str] = Field(default_factory=list)
    reason: str
