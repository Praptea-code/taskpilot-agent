from datetime import UTC, datetime

from agent.core.decomposer import DecomposedTask
from agent.core.scheduler import SchedulingRequest, schedule_tasks
from agent.executors.base import Slot


def task(description: str, effort: int, order: int) -> DecomposedTask:
    return DecomposedTask(description, effort, "focus", order)


def test_greedy_schedule_fits_tasks_with_buffer() -> None:
    start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    request = SchedulingRequest(
        user_id=1,
        tasks=[task("First", 30, 1), task("Second", 45, 2)],
        deadline=None,
        constraints={},
    )

    result = schedule_tasks([Slot(start, end)], request)

    assert result.failure is None
    assert [action.scheduled_at.hour for action in result.actions] == [9, 9]
    assert [action.scheduled_at.minute for action in result.actions] == [0, 40]
    assert [action.duration_minutes for action in result.actions] == [30, 45]


def test_overflow_is_reported() -> None:
    start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    request = SchedulingRequest(
        user_id=1,
        tasks=[task("First", 60, 1), task("Second", 60, 2)],
        deadline=None,
        constraints={},
    )

    result = schedule_tasks([Slot(start, end)], request)

    assert len(result.actions) == 1
    assert result.failure is not None
    assert result.failure.unscheduled == ["Second"]


def test_preferred_days_and_time_window_are_respected() -> None:
    start = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    end = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    request = SchedulingRequest(
        user_id=1,
        tasks=[task("Work", 30, 1)],
        deadline=None,
        constraints={"preferred_days": ["friday"], "earliest_time": "10:00"},
    )

    result = schedule_tasks([Slot(start, end)], request)
    assert result.failure is None
    assert result.actions[0].scheduled_at.hour == 10

    wrong_day = SchedulingRequest(
        user_id=1,
        tasks=[task("Work", 30, 1)],
        deadline=None,
        constraints={"preferred_days": ["monday"]},
    )
    blocked = schedule_tasks([Slot(start, end)], wrong_day)
    assert blocked.actions == []
    assert blocked.failure is not None
