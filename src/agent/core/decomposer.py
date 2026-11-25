from dataclasses import dataclass

from agent.core.clock import Clock
from agent.core.prompts import DECOMPOSE_GOAL_SYSTEM, with_context
from agent.llm.base import LLMClient
from agent.llm.structured import structured
from agent.schemas.llm import ExtractedTask, ExtractedTasks

MIN_EFFORT_MINUTES = 15
DEFAULT_MAX_SESSION_MINUTES = 120


@dataclass(frozen=True)
class DecomposedTask:
    description: str
    estimated_effort_minutes: int
    action_type: str
    order: int


def clamp_tasks(
    tasks: list[ExtractedTask], max_session_minutes: int | None
) -> list[DecomposedTask]:
    maximum = max_session_minutes or DEFAULT_MAX_SESSION_MINUTES
    maximum = max(MIN_EFFORT_MINUTES, maximum)
    result: list[DecomposedTask] = []

    for task in tasks:
        effort = max(MIN_EFFORT_MINUTES, task.estimated_effort_minutes)
        part_number = 1
        while effort > maximum:
            result.append(
                DecomposedTask(
                    description=f"{task.description}, part {part_number}",
                    estimated_effort_minutes=maximum,
                    action_type=task.action_type,
                    order=task.order,
                )
            )
            effort -= maximum
            part_number += 1
        final_description = (
            task.description
            if part_number == 1
            else f"{task.description}, part {part_number}"
        )
        result.append(
            DecomposedTask(
                description=final_description,
                estimated_effort_minutes=effort,
                action_type=task.action_type,
                order=task.order,
            )
        )

    return result


async def decompose_goal(
    title: str,
    constraints: dict[str, object],
    clock: Clock,
    llm: LLMClient,
    user_timezone: str = "UTC",
    examples: str = "",
) -> list[DecomposedTask]:
    maximum = constraints.get("max_session_minutes")
    max_minutes = maximum if isinstance(maximum, int) else None
    system = with_context(DECOMPOSE_GOAL_SYSTEM, clock.now(), user_timezone)
    if examples:
        system = f"{system}\n{examples}"
    user = f"Goal: {title}\nConstraints: {constraints}"
    extracted = await structured(llm, ExtractedTasks, system, user)
    ordered = sorted(extracted.tasks, key=lambda item: item.order)
    return clamp_tasks(ordered, max_minutes)
