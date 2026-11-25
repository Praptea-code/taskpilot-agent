from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_clock, get_current_user_id, get_llm_client, get_registry
from agent.core.clock import Clock
from agent.core.scheduler import ScheduleResult
from agent.core.service import GoalService, PlanOutcome
from agent.db.session import get_session
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.models import Goal, ScheduledAction, Task, User
from agent.schemas.goals import (
    GoalCreate,
    GoalRead,
    PlanResponse,
    ScheduledActionRead,
    ScheduleRead,
    SchedulingFailureRead,
)

router = APIRouter(prefix="/goals", tags=["goals"])


async def load_goal(goal_id: int, user_id: int, session: AsyncSession) -> Goal:
    result = await session.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


def to_schedule(goal: Goal, schedule: ScheduleResult, timezone: str) -> ScheduleRead:
    zone = ZoneInfo(timezone)
    failure = None
    if schedule.failure is not None:
        failure = SchedulingFailureRead(
            unscheduled=schedule.failure.unscheduled,
            reason=schedule.failure.reason,
        )
    return ScheduleRead(
        goal_id=goal.id,
        actions=[
            ScheduledActionRead(
                id=action.id,
                task_id=action.task_id,
                scheduled_at=action.scheduled_at,
                local_time=action.scheduled_at.astimezone(zone).isoformat(),
                duration_minutes=action.duration_minutes,
                status=action.status,
                attempt_number=action.attempt_number,
            )
            for action in schedule.actions
        ],
        failure=failure,
    )


def to_plan(outcome: PlanOutcome, timezone: str) -> PlanResponse:
    schedule = None
    if outcome.schedule is not None:
        schedule = to_schedule(outcome.goal, outcome.schedule, timezone)
    return PlanResponse(
        goal_id=outcome.goal.id,
        status=outcome.goal.status,
        clarifying_question=outcome.clarifying_question,
        schedule=schedule,
    )


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
    registry: ExecutorRegistry = Depends(get_registry),
    clock: Clock = Depends(get_clock),
) -> Goal:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.auto_plan:
        service = GoalService(session, registry, clock)
        outcome = await service.create_goal_plan(user, payload.raw_input_text, payload.domain, llm)
        return outcome.goal

    goal = Goal(user_id=user_id, raw_input_text=payload.raw_input_text, domain=payload.domain)
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


@router.get("", response_model=list[GoalRead])
async def list_goals(
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
) -> list[Goal]:
    result = await session.execute(select(Goal).where(Goal.user_id == user_id))
    return list(result.scalars().all())


@router.get("/{goal_id}", response_model=GoalRead)
async def get_goal(
    goal_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
) -> Goal:
    return await load_goal(goal_id, user_id, session)


@router.post("/{goal_id}/plan", response_model=PlanResponse)
async def plan_goal(
    goal_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
    registry: ExecutorRegistry = Depends(get_registry),
    clock: Clock = Depends(get_clock),
) -> PlanResponse:
    goal = await load_goal(goal_id, user_id, session)
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    service = GoalService(session, registry, clock)
    outcome = await service.create_goal_plan(user, goal.raw_input_text, goal.domain, llm, goal)
    return to_plan(outcome, user.timezone)


@router.get("/{goal_id}/schedule", response_model=ScheduleRead)
async def get_schedule(
    goal_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
) -> ScheduleRead:
    goal = await load_goal(goal_id, user_id, session)
    result = await session.execute(
        select(ScheduledAction)
        .join(Task, ScheduledAction.task_id == Task.id)
        .where(
            ScheduledAction.user_id == user_id,
            Task.goal_id == goal.id,
        )
        .order_by(ScheduledAction.scheduled_at)
    )
    actions = list(result.scalars().all())
    user = await session.get(User, user_id)
    timezone = user.timezone if user is not None else "UTC"
    schedule = ScheduleResult(actions=actions)
    return to_schedule(goal, schedule, timezone)
