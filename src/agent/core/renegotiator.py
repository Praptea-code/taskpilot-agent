from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.clock import Clock
from agent.executors.base import Slot
from agent.executors.registry import ExecutorRegistry
from agent.models import Goal, ScheduledAction, Task, TaskStatus, User


@dataclass(frozen=True)
class RenegotiationContext:
    goal_id: int
    deadline: str
    done_tasks: tuple[str, ...]
    remaining_tasks: tuple[str, ...]
    miss_history: tuple[str, ...]
    free_slots: tuple[Slot, ...]
    text: str


async def build_context(
    session: AsyncSession,
    action: ScheduledAction,
    user: User,
    clock: Clock,
    registry: ExecutorRegistry,
    days: int = 7,
) -> RenegotiationContext:
    task = await session.get(Task, action.task_id)
    if task is None:
        raise ValueError("Scheduled action has no task")
    goal = await session.get(Goal, task.goal_id)
    if goal is None:
        raise ValueError("Task has no goal")

    result = await session.execute(select(Task).where(Task.goal_id == goal.id))
    tasks = list(result.scalars().all())
    done_tasks = tuple(item.description for item in tasks if item.status == TaskStatus.DONE)
    remaining_tasks = tuple(
        item.description for item in tasks if item.status != TaskStatus.DONE
    )
    miss_history = tuple(
        f"{item.description}: {item.miss_count} misses"
        for item in tasks
        if item.miss_count > 0
    )

    start = clock.now()
    end = start + timedelta(days=days)
    executor = registry.get(task.action_type)
    free_slots = tuple(await executor.check_availability(user, start, end, session))

    zone = ZoneInfo(user.timezone)
    deadline = goal.deadline.astimezone(zone).isoformat() if goal.deadline else "none"
    slots_text = (
        ", ".join(
            f"{slot.start.astimezone(zone).isoformat()} to "
            f"{slot.end.astimezone(zone).isoformat()}"
            for slot in free_slots
        )
        or "none"
    )
    text = "\n".join(
        [
            f"Goal: {goal.extracted_goal or goal.raw_input_text}",
            f"Deadline: {deadline}",
            f"Done tasks: {', '.join(done_tasks) or 'none'}",
            f"Remaining tasks: {', '.join(remaining_tasks) or 'none'}",
            f"Miss history: {', '.join(miss_history) or 'none'}",
            f"Free slots: {slots_text}",
        ]
    )
    return RenegotiationContext(
        goal_id=goal.id,
        deadline=deadline,
        done_tasks=done_tasks,
        remaining_tasks=remaining_tasks,
        miss_history=miss_history,
        free_slots=free_slots,
        text=text,
    )
