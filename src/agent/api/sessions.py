from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_clock, get_current_user_id, get_llm_client, get_registry
from agent.core.clock import Clock
from agent.core.inbound import reply_to_session
from agent.db.session import get_session
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.schemas.sessions import SessionReplyCreate, SessionReplyRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/{session_id}/reply", response_model=SessionReplyRead)
async def reply_to_session_endpoint(
    session_id: int,
    payload: SessionReplyCreate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
    registry: ExecutorRegistry = Depends(get_registry),
    clock: Clock = Depends(get_clock),
) -> SessionReplyRead:
    try:
        result = await reply_to_session(
            session, user_id, payload.text, clock, registry, llm, session_id
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return SessionReplyRead(
        session_id=result.session_id or session_id,
        action=result.action or "unclear",
        message_to_user=result.message,
        applied_time=result.applied_time,
        status=result.status or "awaiting_reply",
    )
