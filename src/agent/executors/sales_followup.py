from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agent.channels.email_channel import EmailChannel
from agent.core.clock import Clock
from agent.core.prompts import FOLLOWUP_SYSTEM, with_context
from agent.executors.email_executor import as_utc
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.models import Lead, ScheduledAction, Task, User
from agent.schemas.llm import RenegotiationDecision
from agent.schemas.sales import SendEmailPayload


@dataclass(frozen=True)
class NoReplyOutcome:
    decision: RenegotiationDecision
    email_text: str
    escalation_threshold: int = 3


async def handle_no_reply(
    session: AsyncSession,
    action: ScheduledAction,
    task: Task,
    user: User,
    clock: Clock,
    registry: ExecutorRegistry,
    llm: LLMClient,
    email_channel: EmailChannel,
) -> NoReplyOutcome | None:
    payload = SendEmailPayload.model_validate(task.payload or {})
    lead = await session.get(Lead, payload.lead_id)
    if lead is None:
        return None

    now = clock.now()
    executor = registry.get(task.action_type)
    slots = await executor.check_availability(user, now, now + timedelta(days=7), session)
    next_time = slots[0].start if slots else now + timedelta(days=3)

    last_contacted = as_utc(lead.last_contacted_at) if lead.last_contacted_at else "never"
    prompt = (
        f"Contact: {lead.name}\n"
        f"Company: {lead.company or 'unknown'}\n"
        f"Stage: {lead.stage}\n"
        f"Last contacted: {last_contacted}\n"
        f"Step: {payload.step}"
    )
    system = with_context(FOLLOWUP_SYSTEM, now, user.timezone)
    try:
        email_text = (await llm.complete(system, prompt)).strip()
        if not email_text:
            raise ValueError("Empty follow-up message")
    except Exception:
        email_text = f"Checking in on {lead.name}, step {payload.step}."

    await email_channel.send(
        lead,
        email_text,
        to=lead.email,
        subject=f"Follow-up step {payload.step}",
    )
    decision = RenegotiationDecision(
        action="reschedule",
        new_time=next_time.isoformat(),
        reason="No reply after the previous touch",
        message_to_user=f"Drafted a follow-up and moved it to {next_time.isoformat()}.",
    )
    return NoReplyOutcome(decision, email_text)
