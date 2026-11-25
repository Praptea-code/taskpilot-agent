from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.channels.text_channel import TextChannel
from agent.core.clock import Clock
from agent.core.renegotiator import renegotiate_from_reply
from agent.core.service import GoalService
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.models import AgentSession, ScheduledAction, User
from agent.schemas.channels import InboundMessage


@dataclass(frozen=True)
class InboundResult:
    kind: str
    message: str
    session_id: int | None = None
    goal_id: int | None = None
    status: str | None = None
    action: str | None = None
    applied_time: datetime | None = None


async def find_awaiting_session(
    session: AsyncSession, user_id: int
) -> AgentSession | None:
    result = await session.execute(
        select(AgentSession)
        .where(
            AgentSession.user_id == user_id,
            AgentSession.status == "awaiting_reply",
        )
        .order_by(AgentSession.id.desc())
    )
    return result.scalars().first()


async def reply_to_session(
    session: AsyncSession,
    user_id: int,
    text: str,
    clock: Clock,
    registry: ExecutorRegistry,
    llm: LLMClient,
    session_id: int | None = None,
) -> InboundResult:
    agent_session = await session.get(AgentSession, session_id) if session_id else None
    if agent_session is None:
        agent_session = await find_awaiting_session(session, user_id)
    if agent_session is None:
        raise LookupError("Session not found")
    if agent_session.user_id != user_id:
        raise LookupError("Session not found")
    if agent_session.status != "awaiting_reply":
        raise ValueError("Session is not awaiting a reply")
    if agent_session.scheduled_action_id is None:
        raise LookupError("Action not found")

    action = await session.get(ScheduledAction, agent_session.scheduled_action_id)
    user = await session.get(User, user_id)
    if action is None or user is None:
        raise LookupError("Session context not found")

    context = dict(agent_session.context or {})
    turns = [dict(turn) for turn in context.get("turns", []) if isinstance(turn, dict)]
    history = turns[-10:]
    turns.append({"role": "user", "text": text})
    turns = turns[-10:]

    decision_result = await renegotiate_from_reply(
        session, action, user, clock, registry, llm, text, history
    )
    turns.append({"role": "assistant", "text": decision_result.decision.message_to_user})
    context["turns"] = turns[-10:]
    agent_session.context = context
    agent_session.status = (
        "awaiting_reply" if decision_result.decision.action == "ask_user" else "resolved"
    )
    await TextChannel(session).send(user, decision_result.decision.message_to_user)
    await session.commit()

    return InboundResult(
        kind="renegotiation",
        message=decision_result.decision.message_to_user,
        session_id=agent_session.id,
        status=agent_session.status,
        action=decision_result.decision.action,
        applied_time=decision_result.applied_time,
    )


async def process_inbound(
    session: AsyncSession,
    message: InboundMessage,
    clock: Clock,
    registry: ExecutorRegistry,
    llm: LLMClient,
    session_id: int | None = None,
) -> InboundResult:
    user = await session.get(User, message.user_id)
    if user is None:
        raise LookupError("User not found")
    if session_id is not None or await find_awaiting_session(session, user.id) is not None:
        return await reply_to_session(
            session, user.id, message.text, clock, registry, llm, session_id
        )

    service = GoalService(session, registry, clock)
    outcome = await service.create_goal_plan(user, message.text, "general", llm)
    if outcome.clarifying_question:
        return InboundResult(kind="clarifying", message=outcome.clarifying_question)
    return InboundResult(
        kind="goal",
        message=f"Planned {outcome.goal.extracted_goal}",
        goal_id=outcome.goal.id,
    )
