import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.logging import JsonFormatter
from agent.core.monitor import Monitor, MonitorConfig
from agent.executors.base import CompletionStatus
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import ActionStatus, Base, Goal, ScheduledAction, Task, User

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class DummyExecutor:
    name = "dummy"

    async def check_completion(
        self, action: ScheduledAction, session: object = None
    ) -> CompletionStatus:
        return CompletionStatus.NOT_DONE

    async def check_availability(self, user, start, end, session=None):
        return []

    async def reschedule(self, action, new_time, session=None) -> None:
        return None

    async def cancel(self, action, session=None) -> None:
        return None


def make_monitor(maker: async_sessionmaker, clock: FrozenClock) -> Monitor:
    registry = ExecutorRegistry()
    registry.register("dummy", DummyExecutor())
    responses = [
        json.dumps(
            {
                "action": "keep_as_is",
                "new_time": None,
                "reason": "Wait",
                "message_to_user": "Waiting",
            }
        )
    ]
    return Monitor(
        maker,
        clock,
        MonitorConfig(grace_minutes=10, lock_minutes=15),
        registry,
        FakeLLMClient(responses),
    )


async def test_json_log_formatter_includes_context() -> None:
    record = logging.LogRecord(
        "agent", logging.INFO, __file__, 1, "hello", None, None
    )
    record.user_id = 1
    record.goal_id = 2

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello"
    assert payload["user_id"] == 1
    assert payload["goal_id"] == 2


async def test_downtime_recovery_processes_overdue_action_once(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'overdue.db'}", future=True
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(User(name="User", email="overdue@example.com", timezone="UTC"))
        await session.flush()
        goal = Goal(user_id=1, raw_input_text="Goal", status="planned")
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=1,
            goal_id=goal.id,
            description="Task",
            action_type="dummy",
            estimated_effort_minutes=30,
        )
        session.add(task)
        await session.flush()
        session.add(
            ScheduledAction(
                user_id=1,
                task_id=task.id,
                scheduled_at=START,
                duration_minutes=30,
                status=ActionStatus.SCHEDULED,
                processing_at=START,
            )
        )
        await session.commit()

    clock = FrozenClock(START + timedelta(hours=2))
    monitor = make_monitor(maker, clock)
    await monitor.recover_overdue()

    first = await monitor.tick()
    second = await monitor.tick()

    assert len(first) == 1
    assert second == []
    async with maker() as session:
        task = await session.scalar(select(Task))
        action = await session.scalar(select(ScheduledAction))
        assert task is not None and task.miss_count == 1
        assert action is not None and action.processing_at is None
    await engine.dispose()
