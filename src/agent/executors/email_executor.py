from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.channels.email_channel import EmailChannel
from agent.core.clock import Clock, SystemClock
from agent.executors.base import CompletionStatus, ExecutionResult, Slot
from agent.models import InboxMessage, Lead, ScheduledAction, Task, User
from agent.schemas.sales import SendEmailPayload


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class EmailExecutor:
    name = "send_email"

    def __init__(self, channel: EmailChannel | None = None, clock: Clock | None = None) -> None:
        self.channel = channel or EmailChannel()
        self.clock = clock or SystemClock()

    async def check_availability(
        self,
        user: User,
        start: datetime,
        end: datetime,
        session: AsyncSession | None = None,
    ) -> list[Slot]:
        if session is None:
            return []
        result = await session.execute(select(Lead).where(Lead.user_id == user.id))
        leads = list(result.scalars().all())
        contacts = [
            as_utc(lead.last_contacted_at)
            for lead in leads
            if lead.last_contacted_at is not None
        ]
        last_contact = max(contacts) if contacts else None
        beginning = as_utc(start)
        finish = as_utc(end)
        slots: list[Slot] = []
        for offset in range((finish.date() - beginning.date()).days + 1):
            day = beginning + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            slot_start = datetime.combine(day.date(), time(hour=9), tzinfo=beginning.tzinfo)
            working_end = datetime.combine(
                day.date(), time(hour=21), tzinfo=beginning.tzinfo
            )
            slot_end = min(working_end, finish)
            if slot_start < beginning or slot_end <= slot_start:
                continue
            if last_contact is not None and slot_start - last_contact < timedelta(days=3):
                continue
            slots.append(Slot(slot_start, slot_end))
        return slots

    async def execute(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> ExecutionResult:
        if session is None:
            raise ValueError("EmailExecutor requires a database session")
        task = await session.get(Task, action.task_id)
        if task is None:
            raise ValueError("Email task not found")
        payload = SendEmailPayload.model_validate(task.payload or {})
        lead = await session.get(Lead, payload.lead_id)
        if lead is None or lead.user_id != action.user_id:
            raise ValueError("Email task has no matching lead")

        external_ref = uuid4().hex
        body = f"Template: {payload.template}\nStep: {payload.step}"
        await self.channel.send(
            lead,
            body,
            to=lead.email,
            subject=f"{payload.template} step {payload.step}",
        )
        lead.last_contacted_at = self.clock.now()
        action.external_ref = external_ref
        await session.flush()
        return ExecutionResult(external_ref=external_ref, detail="email sent")

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        if session is None:
            return CompletionStatus.UNKNOWN
        task = await session.get(Task, action.task_id)
        if task is None:
            return CompletionStatus.UNKNOWN
        payload = SendEmailPayload.model_validate(task.payload or {})
        lead = await session.get(Lead, payload.lead_id)
        if lead is None:
            return CompletionStatus.UNKNOWN
        if lead.replied_at is not None:
            return CompletionStatus.DONE

        result = await session.execute(
            select(InboxMessage)
            .where(
                InboxMessage.user_id == action.user_id,
                InboxMessage.lead_id == lead.id,
                InboxMessage.received_at >= as_utc(action.scheduled_at),
            )
            .order_by(InboxMessage.received_at)
        )
        reply = result.scalars().first()
        if reply is None:
            return CompletionStatus.NOT_DONE
        lead.replied_at = reply.received_at
        await session.flush()
        return CompletionStatus.DONE

    async def cancel(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> None:
        return None

    async def reschedule(
        self,
        action: ScheduledAction,
        new_time: datetime,
        session: AsyncSession | None = None,
    ) -> None:
        return None
