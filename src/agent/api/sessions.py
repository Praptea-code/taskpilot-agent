from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_clock, get_current_user_id, get_llm_client, get_registry
from agent.channels.text_channel import TextChannel
from agent.core.clock import Clock
from agent.core.renegotiator import renegotiate_from_reply
from agent.db.session import get_session
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.models import AgentSession, ScheduledAction, User
from agent.schemas.sessions import SessionReplyCreate, SessionReplyRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/{session_id}/reply", response_model=SessionReplyRead)
async def reply_to_session(
    session_id: int,
    payload: SessionReplyCreate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
    registry: ExecutorRegistry = Depends(get_registry),
    clock: Clock = Depends(get_clock),
) -> SessionReplyRead:
    query_result = await session.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == user_id,
        )
    )
    agent_session = query_result.scalar_one_or_none()
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if agent_session.status != "awaiting_reply":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not awaiting a reply"
        )
    if agent_session.scheduled_action_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    action = await session.get(ScheduledAction, agent_session.scheduled_action_id)
    user = await session.get(User, user_id)
    if action is None or user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session context not found"
        )

    context = dict(agent_session.context or {})
    turns = [dict(turn) for turn in context.get("turns", []) if isinstance(turn, dict)]
    history = turns[-10:]
    turns.append({"role": "user", "text": payload.text})
    turns = turns[-10:]

    decision_result = await renegotiate_from_reply(
        session, action, user, clock, registry, llm, payload.text, history
    )
    turns.append({"role": "assistant", "text": decision_result.decision.message_to_user})
    context["turns"] = turns[-10:]
    agent_session.context = context
    agent_session.status = (
        "awaiting_reply" if decision_result.decision.action == "ask_user" else "resolved"
    )
    await TextChannel(session).send(user, decision_result.decision.message_to_user)
    await session.commit()

    return SessionReplyRead(
        session_id=agent_session.id,
        action=decision_result.decision.action,
        message_to_user=decision_result.decision.message_to_user,
        applied_time=decision_result.applied_time,
        status=agent_session.status,
    )
