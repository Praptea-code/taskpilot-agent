import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.renegotiator import build_context, renegotiate
from agent.executors.base import Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    Base,
    Goal,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)
from agent.schemas.llm import RenegotiationDecision

NOW = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RecordingExecutor:
    name = "fake"

    def __init__(self) -> None:
        self.rescheduled: list[datetime] = []
        self.cancelled: list[ScheduledAction] = []

    async def check_availability(
        self, user, start, end, session=None
    ) -> list[Slot]:
        return [Slot(start + timedelta(hours=1), start + timedelta(hours=3))]

    async def reschedule(
        self, action: ScheduledAction, new_time: datetime, session=None
    ) -> None:
        self.rescheduled.append(new_time)

    async def cancel(self, action: ScheduledAction, session=None) -> None:
        self.cancelled.append(action)


async def seed_case(tmp_path, filename: str) -> tuple[
    object,
    async_sessionmaker,
    ExecutorRegistry,
    RecordingExecutor,
    dict[str, int],
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
        drafted = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Draft",
            action_type="focus",
            status=TaskStatus.DONE,
        )
        review = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Review",
            action_type="focus",
            status=TaskStatus.MISSED,
            miss_count=1,
            estimated_effort_minutes=30,
        )
        session.add_all([drafted, review])
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=review.id,
            scheduled_at=NOW - timedelta(hours=1),
            duration_minutes=30,
            status=ActionStatus.MISSED,
            attempt_number=1,
        )
        session.add(action)
        await session.commit()
        ids = {"user": user.id, "goal": goal.id, "task": review.id, "action": action.id}

    executor = RecordingExecutor()
    registry = ExecutorRegistry()
    registry.register("focus", executor)
    return engine, maker, registry, executor, ids


async def test_build_context_includes_goal_tasks_misses_and_slots(tmp_path) -> None:
    engine, maker, registry, _, ids = await seed_case(tmp_path, "context.db")

    async with maker() as session:
        user = await session.get(User, ids["user"])
        action = await session.get(ScheduledAction, ids["action"])
        assert user is not None and action is not None
        context = await build_context(session, action, user, FrozenClock(NOW), registry)

    assert context.goal_id == ids["goal"]
    assert context.done_tasks == ("Draft",)
    assert context.remaining_tasks == ("Review",)
    assert context.miss_history == ("Review: 1 misses",)
    assert len(context.free_slots) == 1
    assert "Goal: Finish report" in context.text
    assert "Deadline:" in context.text
    assert "Done tasks: Draft" in context.text
    assert "Remaining tasks: Review" in context.text
    assert "Miss history: Review: 1 misses" in context.text
    assert "Free slots:" in context.text
    await engine.dispose()


async def test_valid_reschedule_applies_and_increments_attempt(tmp_path) -> None:
    engine, maker, registry, executor, ids = await seed_case(tmp_path, "valid.db")
    proposed = NOW + timedelta(hours=1)
    responses = [
        json.dumps(
            {
                "action": "reschedule",
                "new_time": proposed.isoformat(),
                "reason": "Fits in a free slot",
                "message_to_user": "Moved the action",
            }
        )
    ]

    async with maker() as session:
        user = await session.get(User, ids["user"])
        action = await session.get(ScheduledAction, ids["action"])
        assert user is not None and action is not None
        result = await renegotiate(
            session, action, user, FrozenClock(NOW), registry, FakeLLMClient(responses)
        )

    assert result.applied_time == proposed
    assert as_utc(executor.rescheduled[0]) == proposed

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        task = await session.get(Task, ids["task"])
        assert action is not None and action.status == ActionStatus.SCHEDULED
        assert as_utc(action.scheduled_at) == proposed
        assert action.attempt_number == 2
        assert task is not None and task.status == TaskStatus.SCHEDULED
    await engine.dispose()


async def test_invalid_time_falls_back_to_next_slot(tmp_path) -> None:
    engine, maker, registry, executor, ids = await seed_case(tmp_path, "fallback.db")
    responses = [
        json.dumps(
            {
                "action": "reschedule",
                "new_time": "2026-01-05T09:00:00Z",
                "reason": "Too late",
                "message_to_user": "Moved the action",
            }
        ),
        json.dumps(
            {
                "action": "reschedule",
                "new_time": "2026-01-01T07:00:00Z",
                "reason": "Too early",
                "message_to_user": "Moved the action",
            }
        ),
    ]

    async with maker() as session:
        user = await session.get(User, ids["user"])
        action = await session.get(ScheduledAction, ids["action"])
        assert user is not None and action is not None
        result = await renegotiate(
            session, action, user, FrozenClock(NOW), registry, FakeLLMClient(responses)
        )

    assert as_utc(result.applied_time) == NOW + timedelta(hours=1)
    assert as_utc(executor.rescheduled[0]) == NOW + timedelta(hours=1)
    assert result.decision.reason == "Fallback slot selected"
    await engine.dispose()


async def test_keep_as_is_leaves_state_alone(tmp_path) -> None:
    engine, maker, registry, executor, ids = await seed_case(tmp_path, "keep.db")
    responses = [
        json.dumps(
            {
                "action": "keep_as_is",
                "new_time": None,
                "reason": "The user wants to wait",
                "message_to_user": "Keeping the original plan",
            }
        )
    ]

    async with maker() as session:
        user = await session.get(User, ids["user"])
        action = await session.get(ScheduledAction, ids["action"])
        assert user is not None and action is not None
        result = await renegotiate(
            session, action, user, FrozenClock(NOW), registry, FakeLLMClient(responses)
        )

    assert result.applied_time is None
    assert executor.rescheduled == []
    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        assert action is not None and action.status == ActionStatus.MISSED
        assert action.attempt_number == 1
    await engine.dispose()


def test_renegotiation_decision_schema() -> None:
    decision = RenegotiationDecision.model_validate(
        {
            "action": "reschedule",
            "new_time": "2026-01-02T09:00:00Z",
            "reason": "Busy at the original time",
            "message_to_user": "Moved the action",
        }
    )
    assert decision.action == "reschedule"
    assert decision.new_time == "2026-01-02T09:00:00Z"

    with pytest.raises(ValidationError):
        RenegotiationDecision.model_validate(
            {"action": "unknown", "reason": "Bad", "message_to_user": "Bad"}
        )
