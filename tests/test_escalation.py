from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.escalation import evaluate
from agent.core.monitor import Monitor
from agent.executors.base import CompletionStatus, Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    Base,
    EscalationEvent,
    Goal,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)
from agent.schemas.escalation import EscalationPolicy

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class MissExecutor:
    name = "focus"

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
        return None

    async def cancel(self, action: ScheduledAction, session=None) -> None:
        return None


def make_task(miss_count: int) -> Task:
    return Task(
        user_id=1,
        goal_id=1,
        description="Task",
        action_type="focus",
        miss_count=miss_count,
    )


def test_evaluate_below_threshold() -> None:
    policy = EscalationPolicy(misses_before_escalate=2)

    assert evaluate(make_task(1), policy) is None


def test_evaluate_at_threshold() -> None:
    policy = EscalationPolicy(misses_before_escalate=2)

    decision = evaluate(make_task(2), policy)

    assert decision is not None
    assert decision.level == 1
    assert decision.tone == "insistent"


def test_evaluate_beyond_threshold() -> None:
    policy = EscalationPolicy(misses_before_escalate=2)

    decision = evaluate(make_task(5), policy)

    assert decision is not None
    assert decision.level == 2
    assert decision.tone == "urgent"


async def test_monitor_writes_escalation_event(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'escalation.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(
            name="User",
            email="user@example.com",
            escalation_policy={"misses_before_escalate": 1},
        )
        session.add(user)
        await session.flush()
        goal = Goal(
            user_id=user.id,
            raw_input_text="Goal",
            status="planned",
            deadline=NOW + timedelta(days=2),
            constraints={
                "earliest_time": "00:00",
                "latest_time": "23:59",
                "preferred_days": [],
                "max_session_minutes": 60,
            },
        )
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Task",
            action_type="focus",
            estimated_effort_minutes=30,
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

    registry = ExecutorRegistry()
    registry.register("focus", MissExecutor())
    monitor = Monitor(
        maker,
        FrozenClock(NOW),
        registry=registry,
        llm=FakeLLMClient(
            [
                '{"action": "keep_as_is", "new_time": null, "reason": "Wait", '
                '"message_to_user": "Keeping the plan"}'
            ]
        ),
    )

    await monitor.tick()

    async with maker() as session:
        result = await session.execute(
            select(EscalationEvent).where(EscalationEvent.user_id == 1)
        )
        events = list(result.scalars().all())
        assert len(events) == 1
        assert events[0].level == 1
        assert events[0].channel == "text"
        assert events[0].reason == "Missed 1 times"
    await engine.dispose()
