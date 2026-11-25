from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_current_user_id
from agent.db.session import get_session
from agent.models import Goal
from agent.schemas.goals import GoalCreate, GoalRead

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
) -> Goal:
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
    result = await session.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal
