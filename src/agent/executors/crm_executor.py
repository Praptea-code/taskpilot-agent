from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.clock import Clock, SystemClock
from agent.executors.base import CompletionStatus, ExecutionResult, Slot
from agent.models import Lead, ScheduledAction, Task, User
from agent.schemas.sales import CrmUpdatePayload


class CRMExecutor:
    name = "crm"

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def check_availability(
        self,
        user: User,
        start: datetime,
        end: datetime,
        session: AsyncSession | None = None,
    ) -> list[Slot]:
        return [Slot(start, end)]

    async def execute(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> ExecutionResult:
        if session is None:
            raise ValueError("CRMExecutor requires a database session")
        task = await session.get(Task, action.task_id)
        if task is None:
            raise ValueError("CRM task not found")
        payload = CrmUpdatePayload.model_validate(task.payload or {})
        lead = await session.get(Lead, payload.lead_id)
        if lead is None or lead.user_id != action.user_id:
            raise ValueError("CRM task has no matching lead")

        lead.stage = payload.stage
        lead.last_contacted_at = self.clock.now()
        if payload.note:
            lead.notes = f"{lead.notes}\n{payload.note}".strip()
        external_ref = f"lead-{lead.id}-{payload.stage}"
        action.external_ref = external_ref
        await session.flush()
        return ExecutionResult(external_ref=external_ref, detail="lead updated")

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        if session is None:
            return CompletionStatus.UNKNOWN
        task = await session.get(Task, action.task_id)
        if task is None:
            return CompletionStatus.UNKNOWN
        payload = CrmUpdatePayload.model_validate(task.payload or {})
        lead = await session.get(Lead, payload.lead_id)
        if lead is None:
            return CompletionStatus.UNKNOWN
        return (
            CompletionStatus.DONE
            if lead.stage == payload.stage
            else CompletionStatus.NOT_DONE
        )

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
