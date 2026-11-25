from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent.executors.base import (
    ActionExecutor,
    CompletionStatus,
    ExecutionResult,
    Slot,
)
from agent.models import ScheduledAction, User


class GoogleCalendarExecutor(ActionExecutor):
    name = "google_calendar"

    async def check_availability(
        self,
        user: User,
        start: datetime,
        end: datetime,
        session: AsyncSession | None = None,
    ) -> list[Slot]:
        return []

    async def execute(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> ExecutionResult:
        raise NotImplementedError(
            "Google Calendar OAuth flow is documented but not enabled by default"
        )

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        return CompletionStatus.UNKNOWN

    async def cancel(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> None:
        return None

    async def reschedule(
        self, action: ScheduledAction, new_time: datetime, session: AsyncSession | None = None
    ) -> None:
        return None
