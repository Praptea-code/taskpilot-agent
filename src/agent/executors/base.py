from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from agent.models import ScheduledAction, User


class CompletionStatus(StrEnum):
    DONE = "done"
    NOT_DONE = "not_done"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ExecutionResult:
    external_ref: str | None = None
    success: bool = True
    detail: str | None = None


@runtime_checkable
class ActionExecutor(Protocol):
    name: str

    async def check_availability(
        self, user: User, start: datetime, end: datetime, session: AsyncSession | None = None
    ) -> list[Slot]: ...

    async def execute(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> ExecutionResult: ...

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus: ...

    async def cancel(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> None: ...

    async def reschedule(
        self, action: ScheduledAction, new_time: datetime, session: AsyncSession | None = None
    ) -> None: ...
