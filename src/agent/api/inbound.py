from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_clock, get_llm_client, get_registry
from agent.core.clock import Clock
from agent.core.inbound import process_inbound
from agent.db.session import get_session
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.schemas.channels import InboundMessage, InboundResultRead

router = APIRouter(prefix="/inbound", tags=["inbound"])


@router.post("", response_model=InboundResultRead)
async def inbound_message(
    payload: InboundMessage,
    session: AsyncSession = Depends(get_session),
    llm: LLMClient = Depends(get_llm_client),
    registry: ExecutorRegistry = Depends(get_registry),
    clock: Clock = Depends(get_clock),
) -> InboundResultRead:
    try:
        result = await process_inbound(session, payload, clock, registry, llm)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    return InboundResultRead(
        kind=result.kind,
        message=result.message,
        session_id=result.session_id,
        goal_id=result.goal_id,
        status=result.status,
        action=result.action,
    )
