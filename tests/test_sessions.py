import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.api.deps import get_clock, get_llm_client, get_registry
from agent.core.clock import FrozenClock
from agent.db.session import get_session
from agent.executors.base import Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.main import create_app
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


class ChoiceExecutor:
    name = "fake"

    def __init__(self) -> None:
        self.rescheduled: list[datetime] = []

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ):
        return "not_done"

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


@pytest.fixture
async def session_client(
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

    executor = ChoiceExecutor()
    registry = ExecutorRegistry()
    registry.register("focus", executor)

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(list(responses))
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_clock] = lambda: FrozenClock(NOW)

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
            status=TaskStatus.MISSED,
            estimated_effort_minutes=30,
        )
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW - timedelta(hours=1),
            duration_minutes=30,
            status=ActionStatus.IN_PROGRESS,
            attempt_number=1,
        )
        session.add(action)
        await session.flush()
        agent_session = AgentSession(
            user_id=user.id,
            goal_id=goal.id,
            scheduled_action_id=action.id,
            status="awaiting_reply",
            context={
                "turns": [
                    {"role": "assistant", "text": "You missed the action"},
                ]
            },
        )
        session.add(agent_session)
        await session.commit()
        ids = {
            "user": user.id,
            "goal": goal.id,
            "task": task.id,
            "action": action.id,
            "session": agent_session.id,
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api, maker, responses, ids
    await engine.dispose()


async def test_scripted_multi_turn_reply(session_client) -> None:
    api, maker, responses, ids = session_client
    proposed = NOW + timedelta(hours=1)

    responses.append(
        json.dumps(
            {
                "action": "ask_user",
                "new_time": None,
                "reason": "Need a preference",
                "message_to_user": "Which time works?",
            }
        )
    )
    first = await api.post(
        f"/sessions/{ids['session']}/reply",
        headers={"X-User-Id": "1"},
        json={"text": "Can we do it later?"},
    )
    assert first.status_code == 200
    assert first.json()["action"] == "ask_user"
    assert first.json()["status"] == "awaiting_reply"

    async with maker() as session:
        row = await session.get(AgentSession, ids["session"])
        assert row is not None
        assert len(row.context["turns"]) == 3

    responses.clear()
    responses.append(
        json.dumps(
            {
                "action": "reschedule",
                "new_time": proposed.isoformat(),
                "reason": "User chose a time",
                "message_to_user": "Moved the action",
            }
        )
    )
    second = await api.post(
        f"/sessions/{ids['session']}/reply",
        headers={"X-User-Id": "1"},
        json={"text": "tomorrow morning instead"},
    )
    assert second.status_code == 200
    assert second.json()["action"] == "reschedule"
    assert second.json()["status"] == "resolved"

    async with maker() as session:
        row = await session.get(AgentSession, ids["session"])
        action = await session.get(ScheduledAction, ids["action"])
        notification_result = await session.execute(
            select(Notification).where(Notification.user_id == ids["user"])
        )
        notifications = list(notification_result.scalars().all())
        assert row is not None and row.status == "resolved"
        assert len(row.context["turns"]) == 5
        assert action is not None and action.status == ActionStatus.SCHEDULED
        assert action.scheduled_at.replace(tzinfo=UTC) == proposed
        assert len(notifications) == 2
