from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.service import GoalService
from agent.executors.local_calendar import LocalCalendarExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm import FakeLLMClient
from agent.models import Base, CalendarEvent, Goal, ScheduledAction, Task, User


@pytest.fixture
async def service_env(tmp_path) -> AsyncIterator[tuple[async_sessionmaker, GoalService]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    registry = ExecutorRegistry()
    registry.register("focus", LocalCalendarExecutor(maker))
    clock = FrozenClock(datetime(2026, 1, 1, 8, 0, tzinfo=UTC))

    async with maker() as session:
        yield maker, GoalService(session, registry, clock)

    await engine.dispose()


async def test_create_goal_plan_end_to_end(service_env) -> None:
    maker, service = service_env
    llm = FakeLLMClient(
        [
            '{"title": "Finish the report", "deadline": "by Friday", '
            '"constraints": {"earliest_time": "09:00", "latest_time": "17:00", '
            '"preferred_days": [], "max_session_minutes": 60, "notes": ""}, '
            '"clarifying_question": null}',
            '{"tasks": ['
            '{"description": "Draft", "estimated_effort_minutes": 30, '
            '"action_type": "focus", "order": 1},'
            '{"description": "Review", "estimated_effort_minutes": 20, '
            '"action_type": "focus", "order": 2}'
            ']}',
        ]
    )

    async with maker() as session:
        user = User(name="End", email="end@example.com", timezone="UTC")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    async with maker() as session:
        user = (await session.execute(select(User))).scalar_one()
        live_service = GoalService(
            session,
            service.registry,
            service.clock,
        )
        outcome = await live_service.create_goal_plan(
            user, "Finish report by Friday", "general", llm
        )

    assert outcome.clarifying_question is None
    assert outcome.goal.status == "planned"
    assert outcome.schedule is not None
    assert len(outcome.schedule.actions) == 2

    async with maker() as session:
        goal_count = await session.scalar(select(func.count()).select_from(Goal))
        task_count = await session.scalar(select(func.count()).select_from(Task))
        action_count = await session.scalar(select(func.count()).select_from(ScheduledAction))
        event_count = await session.scalar(select(func.count()).select_from(CalendarEvent))
        assert (goal_count, task_count, action_count, event_count) == (1, 2, 2, 2)
