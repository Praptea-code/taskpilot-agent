import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.api.deps import get_clock, get_llm_client
from agent.core.clock import FrozenClock
from agent.db.session import get_session
from agent.llm.fake import FakeLLMClient
from agent.main import create_app
from agent.models import ActionStatus, Base, Goal, ScheduledAction, Task, TaskStatus, User

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@pytest.fixture
async def checkin_client(
    tmp_path,
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker, list[str], dict[str, int]]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    responses: list[str] = []

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(list(responses))
    app.dependency_overrides[get_clock] = lambda: FrozenClock(NOW)
    transport = httpx.ASGITransport(app=app)

    async with maker() as session:
        user = User(name="User", email="user@example.com")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Goal", status="planned")
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
            scheduled_at=NOW - timedelta(hours=1),
            duration_minutes=30,
            status=ActionStatus.IN_PROGRESS,
        )
        session.add(action)
        await session.commit()
        ids = {"user": user.id, "goal": goal.id, "task": task.id, "action": action.id}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        yield api, maker, responses, ids
    await engine.dispose()


@pytest.mark.parametrize(
    "outcome,new_time,expected_action,expected_task",
    [
        ("completed", None, ActionStatus.DONE, TaskStatus.DONE),
        ("rescheduled", "2026-01-02T09:00:00Z", ActionStatus.SCHEDULED, TaskStatus.SCHEDULED),
        ("cancelled", None, ActionStatus.CANCELLED, TaskStatus.CANCELLED),
        ("unclear", None, ActionStatus.IN_PROGRESS, TaskStatus.SCHEDULED),
    ],
)
async def test_checkin_outcomes(
    checkin_client,
    outcome: str,
    new_time: str | None,
    expected_action: ActionStatus,
    expected_task: TaskStatus,
) -> None:
    api, maker, responses, ids = checkin_client
    responses.append(
        json.dumps(
            {
                "outcome": outcome,
                "new_time": new_time,
                "message_to_user": "ok",
            }
        )
    )

    result = await api.post(
        "/checkins",
        headers={"X-User-Id": "1"},
        json={"scheduled_action_id": ids["action"], "response_text": "yes"},
    )

    assert result.status_code == 201
    body = result.json()
    assert body["outcome"] == outcome
    assert body["scheduled_action_id"] == ids["action"]

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        task = await session.get(Task, ids["task"])
        goal = await session.get(Goal, ids["goal"])
        assert action is not None and action.status == expected_action
        assert task is not None and task.status == expected_task
        if outcome == "rescheduled":
            assert as_utc(action.scheduled_at) == datetime(2026, 1, 2, 9, tzinfo=UTC)
        if outcome == "completed":
            assert goal is not None and goal.status == "done"


async def test_complete_action_stores_checkin(checkin_client) -> None:
    api, maker, _, ids = checkin_client

    result = await api.post(f"/actions/{ids['action']}/complete", headers={"X-User-Id": "1"})

    assert result.status_code == 201
    assert result.json()["outcome"] == "completed"
    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        assert action is not None and action.status == ActionStatus.DONE
