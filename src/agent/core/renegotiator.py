from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.checkin import parse_new_time
from agent.core.clock import Clock
from agent.core.decomposer import DecomposedTask
from agent.core.prompts import RENEGOTIATE_SYSTEM, with_context
from agent.core.scheduler import SchedulingRequest, schedule_tasks
from agent.executors.base import Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.llm.structured import structured
from agent.models import (
    ActionStatus,
    Goal,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)
from agent.schemas.llm import RenegotiationDecision


@dataclass(frozen=True)
class RenegotiationContext:
    goal_id: int
    deadline: str
    deadline_at: datetime | None
    done_tasks: tuple[str, ...]
    remaining_tasks: tuple[str, ...]
    miss_history: tuple[str, ...]
    free_slots: tuple[Slot, ...]
    text: str


@dataclass(frozen=True)
class RenegotiationResult:
    decision: RenegotiationDecision
    applied_time: datetime | None


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
    deadline_at = as_utc(goal.deadline) if goal.deadline is not None else None
    deadline = deadline_at.astimezone(zone).isoformat() if deadline_at else "none"
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
        deadline_at=deadline_at,
        done_tasks=done_tasks,
        remaining_tasks=remaining_tasks,
        miss_history=miss_history,
        free_slots=free_slots,
        text=text,
    )


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_proposed_time(
    decision: RenegotiationDecision,
    context: RenegotiationContext,
    duration_minutes: int,
) -> datetime | None:
    if decision.action != "reschedule":
        return None
    proposed = parse_new_time(decision.new_time)
    if proposed is None:
        return None
    finish = proposed + timedelta(minutes=duration_minutes)
    if context.deadline_at is not None and finish > context.deadline_at:
        return None
    for slot in context.free_slots:
        if slot.start <= proposed and finish <= slot.end:
            return proposed
    return None


def fallback_time(
    context: RenegotiationContext,
    task: Task,
    user: User,
    goal: Goal,
) -> datetime | None:
    item = DecomposedTask(
        description=task.description,
        estimated_effort_minutes=task.estimated_effort_minutes,
        action_type=task.action_type,
        order=1,
    )
    request = SchedulingRequest(
        user_id=user.id,
        tasks=[item],
        deadline=as_utc(goal.deadline) if goal.deadline is not None else None,
        constraints=goal.constraints,
        user_timezone=user.timezone,
    )
    result = schedule_tasks(list(context.free_slots), request)
    return result.actions[0].scheduled_at if result.actions else None


async def decide(
    llm: LLMClient,
    system: str,
    prompt: str,
    context: RenegotiationContext,
    task: Task,
    user: User,
    goal: Goal,
) -> tuple[RenegotiationDecision, datetime | None]:
    decision = await structured(llm, RenegotiationDecision, system, prompt)
    chosen = validate_proposed_time(decision, context, task.estimated_effort_minutes)

    if chosen is None and decision.action == "reschedule":
        retry_text = (
            f"{prompt}\n\nThe previous new_time was invalid. "
            "Choose a time inside a listed free slot and before the deadline."
        )
        decision = await structured(llm, RenegotiationDecision, system, retry_text)
        chosen = validate_proposed_time(decision, context, task.estimated_effort_minutes)

    if chosen is None and decision.action == "reschedule":
        chosen = fallback_time(context, task, user, goal)
        if chosen is not None:
            decision = decision.model_copy(
                update={"new_time": chosen.isoformat(), "reason": "Fallback slot selected"}
            )
    return decision, chosen


async def apply_decision(
    session: AsyncSession,
    action: ScheduledAction,
    registry: ExecutorRegistry,
    decision: RenegotiationDecision,
    chosen: datetime | None,
) -> None:
    task = await session.get(Task, action.task_id)
    if task is None:
        raise ValueError("Scheduled action has no task")
    executor = registry.get(task.action_type)

    if decision.action == "reschedule" and chosen is not None:
        await executor.reschedule(action, chosen, session)
        action.scheduled_at = chosen
        action.status = ActionStatus.SCHEDULED
        task.status = TaskStatus.SCHEDULED
        action.attempt_number += 1
    elif decision.action == "cancel":
        await executor.cancel(action, session)
        action.status = ActionStatus.CANCELLED
        task.status = TaskStatus.CANCELLED
    elif decision.action == "ask_user":
        action.status = ActionStatus.IN_PROGRESS


async def renegotiate(
    session: AsyncSession,
    action: ScheduledAction,
    user: User,
    clock: Clock,
    registry: ExecutorRegistry,
    llm: LLMClient,
) -> RenegotiationResult:
    task = await session.get(Task, action.task_id)
    if task is None:
        raise ValueError("Scheduled action has no task")
    goal = await session.get(Goal, task.goal_id)
    if goal is None:
        raise ValueError("Task has no goal")

    context = await build_context(session, action, user, clock, registry)
    system = with_context(RENEGOTIATE_SYSTEM, clock.now(), user.timezone)
    decision, chosen = await decide(llm, system, context.text, context, task, user, goal)
    await apply_decision(session, action, registry, decision, chosen)
    await session.commit()
    return RenegotiationResult(decision=decision, applied_time=chosen)


async def renegotiate_from_reply(
    session: AsyncSession,
    action: ScheduledAction,
    user: User,
    clock: Clock,
    registry: ExecutorRegistry,
    llm: LLMClient,
    reply_text: str,
    history: list[dict[str, str]],
) -> RenegotiationResult:
    task = await session.get(Task, action.task_id)
    if task is None:
        raise ValueError("Scheduled action has no task")
    goal = await session.get(Goal, task.goal_id)
    if goal is None:
        raise ValueError("Task has no goal")

    context = await build_context(session, action, user, clock, registry)
    system = with_context(RENEGOTIATE_SYSTEM, clock.now(), user.timezone)
    history_text = "\n".join(
        f"{turn['role']}: {turn['text']}" for turn in history
    )
    prompt = (
        f"{context.text}\n\nRecent turns:\n{history_text or 'none'}\n"
        f"User reply: {reply_text}"
    )
    decision, chosen = await decide(llm, system, prompt, context, task, user, goal)
    await apply_decision(session, action, registry, decision, chosen)
    return RenegotiationResult(decision=decision, applied_time=chosen)
