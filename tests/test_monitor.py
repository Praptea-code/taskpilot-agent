import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.monitor import Monitor, sync_database_url
from agent.main import create_app
from agent.models import ActionStatus, Base, Goal, ScheduledAction, Task, User


async def test_tick_finds_only_due_actions(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

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
            scheduled_at=now - timedelta(minutes=11),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
        )
        recent = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=now - timedelta(minutes=9),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
        )
        done = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=now - timedelta(days=1),
            duration_minutes=30,
            status=ActionStatus.DONE,
        )
        session.add_all([due, recent, done])
        await session.commit()
        due_id = due.id

    monitor = Monitor(maker, FrozenClock(now))
    found = await monitor.tick()
    assert [action.id for action in found] == [due_id]
    await engine.dispose()


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
