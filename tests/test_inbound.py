import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.api.deps import get_clock, get_llm_client, get_registry
from agent.core.clock import FrozenClock
from agent.db.session import get_session
from agent.executors.base import CompletionStatus, Slot
from agent.executors.local_calendar import LocalCalendarExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.main import create_app
from agent.models import (
    ActionStatus,
    AgentSession,
    Base,
    Goal,
    ScheduledAction,
    Task,
    User,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class DummyExecutor:
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


@pytest.fixture
async def inbound_client(
    tmp_path,
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker, list[str]]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'inbound.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    responses: list[str] = []

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    registry = ExecutorRegistry()
    registry.register("focus", DummyExecutor())
    registry.register("general", LocalCalendarExecutor(maker))
    registry.register("calendar", LocalCalendarExecutor(maker))

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(list(responses))
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_clock] = lambda: FrozenClock(NOW)

    async with maker() as session:
        session.add(User(name="User", email="user@example.com", timezone="UTC"))
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api, maker, responses
    await engine.dispose()


async def test_inbound_goal_path(inbound_client) -> None:
    api, maker, responses = inbound_client
    responses.extend(
        [
            json.dumps(
                {
                    "title": "Write report",
                    "deadline": "2026-01-03T23:59:00Z",
                    "constraints": {
                        "earliest_time": "00:00",
                        "latest_time": "23:59",
                        "preferred_days": [],
                        "max_session_minutes": 60,
                        "notes": "",
                    },
                    "clarifying_question": None,
                }
            ),
            json.dumps(
                {
                    "tasks": [
                        {
                            "description": "Draft report",
                            "estimated_effort_minutes": 30,
                            "action_type": "general",
                            "order": 1,
                        }
                    ]
                }
            ),
        ]
    )

    response = await api.post(
        "/inbound",
        json={"user_id": 1, "text": "Write a report", "channel": "text"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "goal"
    assert response.json()["goal_id"] == 1
    async with maker() as session:
        goal = await session.get(Goal, 1)
        assert goal is not None and goal.extracted_goal == "Write report"


async def test_inbound_session_path(inbound_client) -> None:
    api, maker, responses = inbound_client
    responses.append(
        json.dumps(
            {
                "action": "keep_as_is",
                "new_time": None,
                "reason": "Wait",
                "message_to_user": "Keeping the plan",
            }
        )
    )
    async with maker() as session:
        goal = Goal(user_id=1, raw_input_text="Goal", status="planned")
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=1,
            goal_id=goal.id,
            description="Task",
            action_type="focus",
            estimated_effort_minutes=30,
        )
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=1,
            task_id=task.id,
            scheduled_at=NOW,
            duration_minutes=30,
            status=ActionStatus.IN_PROGRESS,
        )
        session.add(action)
        await session.flush()
        session.add(
            AgentSession(
                user_id=1,
                goal_id=goal.id,
                scheduled_action_id=action.id,
                status="awaiting_reply",
                context={"turns": []},
            )
        )
        await session.commit()

    response = await api.post(
        "/inbound",
        json={"user_id": 1, "text": "Keep it", "channel": "text"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "renegotiation"
    assert response.json()["status"] == "resolved"
    async with maker() as session:
        row = await session.get(AgentSession, 1)
        assert row is not None and row.status == "resolved"
