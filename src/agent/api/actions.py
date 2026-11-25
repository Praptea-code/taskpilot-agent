from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_clock, get_current_user_id
from agent.core.clock import Clock
from agent.core.state import mark_action_done
from agent.db.session import get_session
from agent.models import CheckIn, ScheduledAction
from agent.schemas.checkins import CheckInRead

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post(
    "/{action_id}/complete", response_model=CheckInRead, status_code=status.HTTP_201_CREATED
)
async def complete_action(
    action_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    clock: Clock = Depends(get_clock),
) -> CheckIn:
    action = await session.get(ScheduledAction, action_id)
    if action is None or action.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    checkin = CheckIn(
        user_id=user_id,
        scheduled_action_id=action.id,
        occurred_at=clock.now(),
        user_response_text=None,
        outcome="completed",
    )
    session.add(checkin)
    await mark_action_done(session, action)
    await session.commit()
    await session.refresh(checkin)
    return checkin
