from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_clock, get_current_user_id, get_llm_client
from agent.core.checkin import classify_checkin, parse_new_time
from agent.core.clock import Clock
from agent.core.state import mark_action_done
from agent.db.session import get_session
from agent.llm.base import LLMClient
from agent.models import ActionStatus, CheckIn, ScheduledAction, Task, TaskStatus, User
from agent.schemas.checkins import CheckInCreate, CheckInRead

router = APIRouter(prefix="/checkins", tags=["checkins"])


@router.post("", response_model=CheckInRead, status_code=status.HTTP_201_CREATED)
async def create_checkin(
    payload: CheckInCreate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
    clock: Clock = Depends(get_clock),
) -> CheckIn:
    action = await session.get(ScheduledAction, payload.scheduled_action_id)
    if action is None or action.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    decision = await classify_checkin(payload.response_text, user, clock, llm)
    checkin = CheckIn(
        user_id=user_id,
        scheduled_action_id=action.id,
        occurred_at=clock.now(),
        user_response_text=payload.response_text,
        outcome=decision.outcome,
    )
    session.add(checkin)
    task = await session.get(Task, action.task_id)

    if decision.outcome == "completed":
        await mark_action_done(session, action)
    elif decision.outcome == "cancelled":
        action.status = ActionStatus.CANCELLED
        if task is not None:
            task.status = TaskStatus.CANCELLED
    elif decision.outcome == "rescheduled":
        new_time = parse_new_time(decision.new_time)
        if new_time is not None:
            action.scheduled_at = new_time
            action.status = ActionStatus.SCHEDULED
            if task is not None:
                task.status = TaskStatus.SCHEDULED
        else:
            action.status = ActionStatus.IN_PROGRESS
    else:
        action.status = ActionStatus.IN_PROGRESS

    await session.commit()
    await session.refresh(checkin)
    return checkin
