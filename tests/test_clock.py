from datetime import UTC, datetime, timedelta

from agent.core.clock import Clock, FrozenClock, SystemClock
from agent.core.prompts import with_context


async def test_frozen_clock_is_stable_and_advances() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    clock = FrozenClock(start)

    assert clock.now() == start
    clock.advance(timedelta(hours=2))
    assert clock.now() == start + timedelta(hours=2)
    assert clock.now() == start + timedelta(hours=2)


async def test_system_clock_uses_utc() -> None:
    clock: Clock = SystemClock()
    value = clock.now()
    assert value.tzinfo is not None


def test_prompt_context_includes_time_and_timezone() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    prompt = with_context("Base prompt", now, "Asia/Kathmandu")
    assert "Base prompt" in prompt
    assert "2026-01-01" in prompt
    assert "Asia/Kathmandu" in prompt
