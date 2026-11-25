from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.executors.base import ActionExecutor, CompletionStatus
from agent.executors.local_calendar import LocalCalendarExecutor, as_utc
from agent.models import Base, CalendarEvent, Goal, ScheduledAction, Task, User


@pytest.fixture
async def calendar_env(tmp_path) -> AsyncIterator[tuple[async_sessionmaker, User, ScheduledAction]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'calendar.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(name="Cal", email="cal@example.com", timezone="UTC")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Plan")
        session.add(goal)
        await session.flush()
        task = Task(user_id=user.id, goal_id=goal.id, description="Work", action_type="focus")
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
            duration_minutes=30,
        )
        session.add(action)
        await session.commit()
        await session.refresh(user)
        await session.refresh(action)
        yield maker, user, action

    await engine.dispose()


async def test_free_slots_exclude_overlapping_events(calendar_env) -> None:
    maker, user, _ = calendar_env
    executor = LocalCalendarExecutor(maker)
    assert isinstance(executor, ActionExecutor)

    async with maker() as session:
        session.add(
            CalendarEvent(
                user_id=user.id,
                title="Busy",
                start_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
            )
        )
        await session.commit()

    start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    slots = await executor.check_availability(user, start, end)

    assert [(slot.start.hour, slot.end.hour) for slot in slots] == [(9, 10), (11, 12)]


async def test_execute_completion_reschedule_and_cancel(calendar_env) -> None:
    maker, _, action = calendar_env
    executor = LocalCalendarExecutor(maker)

    result = await executor.execute(action)
    assert result.success is True
    assert result.external_ref is not None
    assert await executor.check_completion(action) is CompletionStatus.NOT_DONE

    async with maker() as session:
        event = (await session.execute(select(CalendarEvent))).scalar_one()
        event.done = True
        await session.commit()

    assert await executor.check_completion(action) is CompletionStatus.DONE

    new_time = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
    await executor.reschedule(action, new_time)
    async with maker() as session:
        event = (await session.execute(select(CalendarEvent))).scalar_one()
        assert as_utc(event.start_at) == new_time
        assert as_utc(event.end_at) == new_time + timedelta(minutes=30)

    await executor.cancel(action)
    async with maker() as session:
        assert (await session.execute(select(CalendarEvent))).scalar_one_or_none() is None
