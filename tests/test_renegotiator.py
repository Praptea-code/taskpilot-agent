from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.core.renegotiator import build_context
from agent.executors.base import Slot
from agent.executors.registry import ExecutorRegistry
from agent.models import Base, Goal, ScheduledAction, Task, TaskStatus, User
from agent.schemas.llm import RenegotiationDecision

NOW = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


class SlotExecutor:
    name = "fake"

    async def check_availability(
        self, user, start, end, session=None
    ) -> list[Slot]:
        return [Slot(start + timedelta(hours=1), start + timedelta(hours=2))]


async def test_build_context_includes_goal_tasks_misses_and_slots(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
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
            status=TaskStatus.SCHEDULED,
            miss_count=2,
        )
        session.add_all([drafted, review])
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=review.id,
            scheduled_at=NOW - timedelta(hours=1),
            duration_minutes=30,
            status="missed",
        )
        session.add(action)
        await session.commit()
        user_id = user.id
        goal_id = goal.id
        action_id = action.id

    registry = ExecutorRegistry()
    registry.register("focus", SlotExecutor())

    async with maker() as session:
        user = await session.get(User, user_id)
        action = await session.get(ScheduledAction, action_id)
        assert user is not None and action is not None
        context = await build_context(session, action, user, FrozenClock(NOW), registry)

    assert context.goal_id == goal_id
    assert context.done_tasks == ("Draft",)
    assert context.remaining_tasks == ("Review",)
    assert context.miss_history == ("Review: 2 misses",)
    assert len(context.free_slots) == 1
    assert "Goal: Finish report" in context.text
    assert "Deadline:" in context.text
    assert "Done tasks: Draft" in context.text
    assert "Remaining tasks: Review" in context.text
    assert "Miss history: Review: 2 misses" in context.text
    assert "Free slots:" in context.text
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
