import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.monitor import Monitor, sync_database_url
from agent.executors.base import CompletionStatus, Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.main import create_app
from agent.models import (
    ActionStatus,
    Base,
    Goal,
    GoalStatus,
    Notification,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeCompletionExecutor:
    name = "fake"

    def __init__(self, status: CompletionStatus) -> None:
        self.status = status

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        return self.status

    async def check_availability(
        self, user, start, end, session=None
    ) -> list[Slot]:
        return [Slot(start + timedelta(hours=1), start + timedelta(hours=3))]

    async def reschedule(
        self, action: ScheduledAction, new_time: datetime, session=None
    ) -> None:
        return None

    async def cancel(self, action: ScheduledAction, session=None) -> None:
        return None


def make_registry(status: CompletionStatus) -> ExecutorRegistry:
    registry = ExecutorRegistry()
    registry.register("focus", FakeCompletionExecutor(status))
    return registry


async def seed_due_action(tmp_path: Path, filename: str = "test.db") -> tuple[
    async_sessionmaker[AsyncSession], dict[str, int]
]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / filename}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(name="User", email="user@example.com")
        session.add(user)
        await session.flush()
        goal = Goal(
            user_id=user.id,
            raw_input_text="Goal",
            status=GoalStatus.PLANNED,
        )
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Task",
            action_type="focus",
            status=TaskStatus.SCHEDULED,
        )
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW - timedelta(minutes=11),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
        )
        session.add(action)
        await session.commit()
        ids = {"user": user.id, "goal": goal.id, "task": task.id, "action": action.id}
    return maker, ids


async def test_tick_finds_only_due_actions(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scan.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(name="User", email="user@example.com")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Goal")
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Task",
            action_type="focus",
        )
        session.add(task)
        await session.flush()
        due = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW - timedelta(minutes=11),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
        )
        recent = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW - timedelta(minutes=9),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
        )
        done = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW - timedelta(days=1),
            duration_minutes=30,
            status=ActionStatus.DONE,
        )
        session.add_all([due, recent, done])
        await session.commit()
        due_id = due.id

    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        registry=make_registry(CompletionStatus.UNKNOWN),
    )
    found = await monitor.tick()
    assert [action.id for action in found] == [due_id]
    await engine.dispose()


async def test_done_marks_action_task_and_goal_done(tmp_path) -> None:
    maker, ids = await seed_due_action(tmp_path, "done.db")
    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        registry=make_registry(CompletionStatus.DONE),
    )

    await monitor.tick()

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        task = await session.get(Task, ids["task"])
        goal = await session.get(Goal, ids["goal"])
        assert action is not None and action.status == ActionStatus.DONE
        assert task is not None and task.status == TaskStatus.DONE
        assert goal is not None and goal.status == GoalStatus.DONE


async def test_not_done_marks_missed_and_increments_miss_count(tmp_path) -> None:
    maker, ids = await seed_due_action(tmp_path, "missed.db")
    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        registry=make_registry(CompletionStatus.NOT_DONE),
        llm=FakeLLMClient(
            [
                json.dumps(
                    {
                        "action": "keep_as_is",
                        "new_time": None,
                        "reason": "Wait",
                        "message_to_user": "Keeping the plan",
                    }
                )
            ]
        ),
    )

    await monitor.tick()

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        task = await session.get(Task, ids["task"])
        assert action is not None and action.status == ActionStatus.MISSED
        assert task is not None and task.status == TaskStatus.MISSED
        assert task.miss_count == 1


async def test_unknown_creates_one_check_in_notification(tmp_path) -> None:
    maker, ids = await seed_due_action(tmp_path, "unknown.db")
    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        registry=make_registry(CompletionStatus.UNKNOWN),
    )

    await monitor.tick()
    await monitor.tick()

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        result = await session.execute(
            select(Notification).where(Notification.user_id == ids["user"])
        )
        notifications = list(result.scalars().all())
        assert action is not None and action.status == ActionStatus.IN_PROGRESS
        assert len(notifications) == 1
        assert notifications[0].title == "Check-in"


async def test_monitor_start_stop(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monitor = Monitor(maker, FrozenClock(datetime(2026, 1, 1, tzinfo=UTC)))
    jobstore_url = f"sqlite:///{tmp_path / 'jobs.db'}"

    await monitor.start(jobstore_url)
    assert monitor.scheduler.running
    monitor.stop()
    await asyncio.sleep(0)
    assert not monitor.scheduler.running
    await engine.dispose()


def test_sync_database_url() -> None:
    assert sync_database_url("sqlite+aiosqlite:///./agent.db") == "sqlite:///./agent.db"
    assert sync_database_url("postgresql+asyncpg://u:p@host/db") == "postgresql://u:p@host/db"


def test_app_exposes_monitor() -> None:
    app = create_app()
    assert isinstance(app.state.monitor, Monitor)
