import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.api.deps import get_clock, get_llm_client, get_registry, get_voice_channel
from agent.core.clock import FrozenClock
from agent.db.session import get_session
from agent.executors.base import CompletionStatus
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

    async def check_availability(self, user, start, end, session=None):
        return []

    async def reschedule(self, action, new_time, session=None) -> None:
        return None

    async def cancel(self, action, session=None) -> None:
        return None


class StubVoice:
    def __init__(self) -> None:
        self.transcribed: list[bytes] = []

    async def transcribe(self, audio_bytes: bytes) -> str:
        self.transcribed.append(audio_bytes)
        return "Keep it"

    async def synthesize(self, text: str) -> bytes:
        return b"RIFF" + text.encode("utf-8")


@pytest.fixture
async def voice_client(
    tmp_path,
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker, StubVoice]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'voice.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    registry = ExecutorRegistry()
    registry.register("focus", DummyExecutor())
    voice = StubVoice()
    responses = [
        json.dumps(
            {
                "action": "keep_as_is",
                "new_time": None,
                "reason": "Wait",
                "message_to_user": "Keeping the plan",
            }
        )
    ]

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(list(responses))
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_clock] = lambda: FrozenClock(NOW)
    app.dependency_overrides[get_voice_channel] = lambda: voice

    async with maker() as session:
        session.add(User(name="User", email="user@example.com", timezone="UTC"))
        await session.flush()
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

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api, maker, voice
    await engine.dispose()


async def test_voice_endpoint_round_trip(voice_client) -> None:
    api, maker, voice = voice_client

    response = await api.post(
        "/voice",
        headers={"X-User-Id": "1"},
        files={"audio": ("clip.wav", b"fake audio", "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "renegotiation"
    assert body["text"] == "Keeping the plan"
    assert body["audio_format"] == "wav"
    assert base64.b64decode(body["audio_base64"]) == b"RIFFKeeping the plan"
    assert voice.transcribed == [b"fake audio"]
    async with maker() as session:
        row = await session.get(AgentSession, 1)
        assert row is not None and row.status == "resolved"
