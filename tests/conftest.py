from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.api.deps import get_clock, get_llm_client, get_registry
from agent.core.clock import FrozenClock
from agent.db.session import get_session
from agent.executors.local_calendar import LocalCalendarExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm import FakeLLMClient
from agent.main import create_app
from agent.models import Base, User

PLAN_RESPONSES = [
    '{"title": "Finish the report", "deadline": "by Friday", '
    '"constraints": {"earliest_time": "09:00", "latest_time": "17:00", '
    '"preferred_days": [], "max_session_minutes": 60, "notes": ""}, '
    '"clarifying_question": null}',
    '{"tasks": ['
    '{"description": "Draft", "estimated_effort_minutes": 30, '
    '"action_type": "focus", "order": 1},'
    '{"description": "Review", "estimated_effort_minutes": 20, '
    '"action_type": "focus", "order": 2}'
    ']}',
]


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    registry = ExecutorRegistry()
    registry.register("focus", LocalCalendarExecutor(maker))

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(PLAN_RESPONSES)
    app.dependency_overrides[get_clock] = lambda: FrozenClock(
        datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    )
    app.dependency_overrides[get_registry] = lambda: registry
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        async with maker() as session:
            session.add_all(
                [
                    User(name="User A", email="a@example.com"),
                    User(name="User B", email="b@example.com"),
                ]
            )
            await session.commit()
        yield test_client, maker

    await engine.dispose()
