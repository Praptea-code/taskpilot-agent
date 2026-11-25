import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.monitor import Monitor, MonitorConfig
from agent.executors.base import CompletionStatus, Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    AgentSession,
    Base,
    Goal,
    Notification,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class MissingExecutor:
    name = "fake"

    def __init__(self) -> None:
        self.rescheduled: list[datetime] = []

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        return CompletionStatus.NOT_DONE

    async def check_availability(
        self, user, start, end, session=None
    ) -> list[Slot]:
        return [Slot(start + timedelta(hours=1), start + timedelta(hours=3))]

    async def reschedule(
        self, action: ScheduledAction, new_time: datetime, session=None
    ) -> None:
        self.rescheduled.append(new_time)

    async def cancel(self, action: ScheduledAction, session=None) -> None:
        return None


async def seed_missing_action(tmp_path: Path, filename: str) -> tuple[
    object, async_sessionmaker, ExecutorRegistry, MissingExecutor, dict[str, int]
]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / filename}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(name="User", email="user@example.com", timezone="UTC")
        session.add(user)
        await session.flush()
        goal = Goal(
            user_id=user.id,
            raw_input_text="Finish report",
            extracted_goal="Finish report",
            deadline=NOW + timedelta(days=3),
            constraints={
                "earliest_time": "00:00",
                "latest_time": "23:59",
                "preferred_days": [],
                "max_session_minutes": 60,
            },
            status="planned",
        )
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Draft",
            action_type="focus",
            status=TaskStatus.SCHEDULED,
            estimated_effort_minutes=30,
        )
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW - timedelta(minutes=11),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
            attempt_number=1,
        )
        session.add(action)
        await session.commit()
        ids = {"user": user.id, "goal": goal.id, "task": task.id, "action": action.id}

    executor = MissingExecutor()
    registry = ExecutorRegistry()
    registry.register("focus", executor)
    return engine, maker, registry, executor, ids


async def test_missed_action_is_rescheduled_and_notifies(tmp_path) -> None:
    engine, maker, registry, executor, ids = await seed_missing_action(tmp_path, "reschedule.db")
    proposed = NOW + timedelta(hours=1)
    responses = [
        json.dumps(
            {
                "action": "reschedule",
                "new_time": proposed.isoformat(),
                "reason": "Free slot available",
                "message_to_user": "Moved the action",
            }
        )
    ]
    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        MonitorConfig(grace_minutes=10),
        registry,
        FakeLLMClient(responses),
    )

    await monitor.tick()

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        task = await session.get(Task, ids["task"])
        notification_result = await session.execute(
            select(Notification).where(Notification.user_id == ids["user"])
        )
        notifications = list(notification_result.scalars().all())
        assert action is not None and action.status == ActionStatus.SCHEDULED
        assert action.scheduled_at.replace(tzinfo=UTC) == proposed
        assert action.attempt_number == 2
        assert task is not None and task.miss_count == 1
        assert len(notifications) == 1
        assert notifications[0].body == "Moved the action"
    assert len(executor.rescheduled) == 1
    await engine.dispose()


async def test_ask_user_creates_session(tmp_path) -> None:
    engine, maker, registry, _, ids = await seed_missing_action(tmp_path, "ask.db")
    responses = [
        json.dumps(
            {
                "action": "ask_user",
                "new_time": None,
                "reason": "User preference needed",
                "message_to_user": "When should we do this?",
            }
        )
    ]
    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        MonitorConfig(grace_minutes=10),
        registry,
        FakeLLMClient(responses),
    )

    await monitor.tick()

    async with maker() as session:
        result = await session.execute(
            select(AgentSession).where(AgentSession.user_id == ids["user"])
        )
        sessions = list(result.scalars().all())
        assert len(sessions) == 1
        assert sessions[0].status == "awaiting_reply"
        assert sessions[0].goal_id == ids["goal"]
    await engine.dispose()
