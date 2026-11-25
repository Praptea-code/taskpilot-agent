from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.db.session import get_sessionmaker
from agent.executors.base import CompletionStatus, ExecutionResult, Slot
from agent.models import CalendarEvent, ScheduledAction, User


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def subtract_busy(windows: list[Slot], busy: list[Slot]) -> list[Slot]:
    free: list[Slot] = []
    for window in windows:
        pieces = [window]
        for event in busy:
            remaining: list[Slot] = []
            for piece in pieces:
                if event.end <= piece.start or event.start >= piece.end:
                    remaining.append(piece)
                    continue
                if event.start > piece.start:
                    remaining.append(Slot(piece.start, event.start))
                if event.end < piece.end:
                    remaining.append(Slot(event.end, piece.end))
            pieces = remaining
        free.extend(pieces)
    return free


class LocalCalendarExecutor:
    name = "local_calendar"

    def __init__(self, maker: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._maker = maker or get_sessionmaker()

    @asynccontextmanager
    async def _scope(
        self, session: AsyncSession | None
    ) -> AsyncIterator[tuple[AsyncSession, bool]]:
        if session is not None:
            yield session, False
        else:
            async with self._maker() as own:
                yield own, True

    def working_windows(self, user: User, start: datetime, end: datetime) -> list[Slot]:
        zone = ZoneInfo(user.timezone)
        prefs = user.notification_prefs or {}
        begin_text = str(prefs.get("working_hours_start", "09:00"))
        finish_text = str(prefs.get("working_hours_end", "21:00"))
        begin_hour = int(begin_text.split(":")[0])
        finish_hour = int(finish_text.split(":")[0])

        local_start = start.astimezone(zone)
        local_end = end.astimezone(zone)
        current = local_start.date()
        windows: list[Slot] = []
        while current <= local_end.date():
            window_start = datetime(
                current.year, current.month, current.day, begin_hour, tzinfo=zone
            ).astimezone(UTC)
            window_end = datetime(
                current.year, current.month, current.day, finish_hour, tzinfo=zone
            ).astimezone(UTC)
            clipped_start = max(start, window_start)
            clipped_end = min(end, window_end)
            if clipped_start < clipped_end:
                windows.append(Slot(clipped_start, clipped_end))
            current += timedelta(days=1)
        return windows

    async def check_availability(
        self,
        user: User,
        start: datetime,
        end: datetime,
        session: AsyncSession | None = None,
    ) -> list[Slot]:
        async with self._scope(session) as (active, _):
            result = await active.execute(
                select(CalendarEvent).where(
                    CalendarEvent.user_id == user.id,
                    CalendarEvent.start_at < end,
                    CalendarEvent.end_at > start,
                )
            )
            busy = [
                Slot(as_utc(event.start_at), as_utc(event.end_at))
                for event in result.scalars().all()
            ]
        return subtract_busy(self.working_windows(user, start, end), busy)

    async def execute(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> ExecutionResult:
        end_at = action.scheduled_at + timedelta(minutes=action.duration_minutes)
        async with self._scope(session) as (active, owns):
            event = CalendarEvent(
                user_id=action.user_id,
                title=f"Action {action.id}",
                start_at=action.scheduled_at,
                end_at=end_at,
            )
            active.add(event)
            await active.flush()
            await active.refresh(event)
            if owns:
                await active.commit()
            return ExecutionResult(external_ref=str(event.id))

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        async with self._scope(session) as (active, _):
            result = await active.execute(
                select(CalendarEvent).where(
                    CalendarEvent.user_id == action.user_id,
                    CalendarEvent.title == f"Action {action.id}",
                )
            )
            event = result.scalar_one_or_none()
        if event is None:
            return CompletionStatus.UNKNOWN
        return CompletionStatus.DONE if event.done else CompletionStatus.NOT_DONE

    async def cancel(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> None:
        async with self._scope(session) as (active, owns):
            result = await active.execute(
                select(CalendarEvent).where(
                    CalendarEvent.user_id == action.user_id,
                    CalendarEvent.title == f"Action {action.id}",
                )
            )
            event = result.scalar_one_or_none()
            if event is not None:
                await active.delete(event)
                if owns:
                    await active.commit()

    async def reschedule(
        self,
        action: ScheduledAction,
        new_time: datetime,
        session: AsyncSession | None = None,
    ) -> None:
        end_at = new_time + timedelta(minutes=action.duration_minutes)
        async with self._scope(session) as (active, owns):
            result = await active.execute(
                select(CalendarEvent).where(
                    CalendarEvent.user_id == action.user_id,
                    CalendarEvent.title == f"Action {action.id}",
                )
            )
            event = result.scalar_one_or_none()
            if event is not None:
                event.start_at = new_time
                event.end_at = end_at
                if owns:
                    await active.commit()
