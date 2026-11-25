from datetime import UTC, datetime

from agent.core.clock import FrozenClock
from agent.core.decomposer import clamp_tasks, decompose_goal
from agent.llm import FakeLLMClient
from agent.schemas.llm import ExtractedTask


async def test_decompose_goal_with_fake_llm() -> None:
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    llm = FakeLLMClient(
        [
            '{"tasks": ['
            '{"description": "Draft outline", "estimated_effort_minutes": 30, '
            '"action_type": "focus", "order": 2},'
            '{"description": "Collect notes", "estimated_effort_minutes": 20, '
            '"action_type": "focus", "order": 1}'
            ']}'
        ]
    )

    tasks = await decompose_goal("Write a report", {}, clock, llm)

    assert [task.description for task in tasks] == ["Collect notes", "Draft outline"]
    assert [task.estimated_effort_minutes for task in tasks] == [20, 30]


def test_clamp_effort_and_split_large_tasks() -> None:
    tasks = [
        ExtractedTask(
            description="Tiny step",
            estimated_effort_minutes=2,
            action_type="focus",
            order=1,
        ),
        ExtractedTask(
            description="Huge step",
            estimated_effort_minutes=130,
            action_type="focus",
            order=2,
        ),
    ]

    clamped = clamp_tasks(tasks, 60)

    assert [task.estimated_effort_minutes for task in clamped] == [15, 60, 60, 10]
    assert clamped[1].description == "Huge step, part 1"
    assert clamped[3].description == "Huge step, part 3"
