from datetime import UTC, datetime

from agent.core.clock import FrozenClock
from agent.core.extractor import extract_goal
from agent.llm import FakeLLMClient
from agent.models import User


async def test_extract_goal_resolves_relative_deadline_to_utc() -> None:
    user = User(name="Test", email="test@example.com", timezone="Asia/Kathmandu")
    clock = FrozenClock(datetime(2026, 1, 7, 12, 0, tzinfo=UTC))
    llm = FakeLLMClient(
        [
            '{"title": "Finish the report", "deadline": "by Friday", '
            '"constraints": {"earliest_time": "09:00", "latest_time": "17:00", '
            '"preferred_days": [], "max_session_minutes": 60, "notes": ""}, '
            '"clarifying_question": null}'
        ]
    )

    result = await extract_goal("Finish my report by Friday", user, clock, llm)

    assert result.title == "Finish the report"
    assert result.deadline is not None
    assert result.deadline.tzinfo is UTC
    assert result.deadline.date().isoformat() == "2026-01-09"
    assert result.constraints["max_session_minutes"] == 60
    assert result.clarifying_question is None
    assert "Friday" in llm.calls[0].system
