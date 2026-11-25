import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.channels.email_channel import EmailChannel
from agent.channels.text_channel import TextChannel
from agent.config import get_settings
from agent.core.clock import Clock, SystemClock
from agent.core.escalation import escalation_message, escalation_policy_for, evaluate
from agent.core.renegotiator import apply_decision, renegotiate
from agent.core.state import finish_goal_if_done
from agent.db.session import get_sessionmaker
from agent.executors.base import CompletionStatus
from agent.executors.domain_prompts import handler_for
from agent.executors.registry import ExecutorRegistry, build_default_registry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm
from agent.models import (
    ActionStatus,
    AgentSession,
    EscalationEvent,
    Goal,
    Notification,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)
from agent.schemas.escalation import EscalationPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitorConfig:
    grace_minutes: int = 10
    interval_seconds: int = 30
    lock_minutes: int = 15


def sync_database_url(url: str) -> str:
    return url.replace("+aiosqlite", "").replace("+asyncpg", "").replace("+asyncmy", "")


async def scheduled_tick() -> None:
    settings = get_settings()
    maker = get_sessionmaker(settings.database_url)
    monitor = Monitor(
        maker,
        SystemClock(),
        MonitorConfig(grace_minutes=settings.grace_minutes),
        build_default_registry(maker),
    )
    await monitor.tick()


class Monitor:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        clock: Clock | None = None,
        config: MonitorConfig | None = None,
        registry: ExecutorRegistry | None = None,
        llm: LLMClient | None = None,
        email_channel: EmailChannel | None = None,
    ) -> None:
        self.maker = maker
        self.clock = clock or SystemClock()
        self.config = config or MonitorConfig()
        self.registry = registry or ExecutorRegistry()
        self.llm = llm or get_llm()
        self.email_channel = email_channel or EmailChannel()
        self.scheduler = AsyncIOScheduler()

    async def recover_overdue(self) -> None:
        stale_before = self.clock.now() - timedelta(minutes=self.config.lock_minutes)
        async with self.maker() as session:
            await session.execute(
                update(ScheduledAction)
                .where(
                    ScheduledAction.processing_at.is_not(None),
                    ScheduledAction.processing_at <= stale_before,
                )
                .values(processing_at=None)
            )
            await session.commit()

    async def start(self, jobstore_url: str) -> None:
        if self.scheduler.running:
            return
        try:
            await self.recover_overdue()
        except OperationalError:
            logger.warning("monitor_recovery_skipped", extra={"reason": "schema not ready"})
        jobstore = SQLAlchemyJobStore(url=sync_database_url(jobstore_url))
        self.scheduler.configure(jobstores={"default": jobstore})
        self.scheduler.add_job(
            scheduled_tick,
            "interval",
            seconds=self.config.interval_seconds,
            id="monitor_tick",
            replace_existing=True,
        )
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def tick(self) -> list[ScheduledAction]:
        now = self.clock.now()
        cutoff = now - timedelta(minutes=self.config.grace_minutes)
        await self.recover_overdue()
        claimed: list[ScheduledAction] = []
        async with self.maker() as session:
            result = await session.execute(
                select(ScheduledAction)
                .where(
                    ScheduledAction.status == ActionStatus.SCHEDULED,
                    ScheduledAction.scheduled_at <= cutoff,
                    ScheduledAction.processing_at.is_(None),
                )
                .order_by(ScheduledAction.id)
            )
            for action in result.scalars().all():
                claim = await session.execute(
                    update(ScheduledAction)
                    .where(
                        ScheduledAction.id == action.id,
                        ScheduledAction.processing_at.is_(None),
                        ScheduledAction.attempt_number == action.attempt_number,
                    )
                    .values(processing_at=now)
                )
                if claim.rowcount == 1:
                    claimed.append(action)
            await session.commit()
            for action in claimed:
                await self.process(session, action)
            return claimed

    async def _record_escalation(
        self,
        session: AsyncSession,
        task: Task,
        user: User,
        policy: EscalationPolicy,
    ) -> None:
        escalation = evaluate(task, policy)
        if escalation is None:
            return
        session.add(
            EscalationEvent(
                user_id=user.id,
                goal_id=task.goal_id,
                reason=escalation.reason,
                level=escalation.level,
                channel=escalation.channel,
                occurred_at=self.clock.now(),
            )
        )
        message = await escalation_message(task, escalation, user, self.clock, self.llm)
        await TextChannel(session).send(user, message)
        if escalation.level >= 2:
            for contact in escalation.notify_contacts:
                await self.email_channel.send(
                    user,
                    message,
                    to=contact,
                    subject=f"Escalation level {escalation.level}",
                )

    async def process(self, session: AsyncSession, action: ScheduledAction) -> None:
        task = await session.get(Task, action.task_id)
        if task is None:
            action.processing_at = None
            await session.commit()
            return
        executor = self.registry.get(task.action_type)
        status = await executor.check_completion(action, session)

        if status == CompletionStatus.DONE:
            action.status = ActionStatus.DONE
            task.status = TaskStatus.DONE
            await finish_goal_if_done(session, task.goal_id)
        elif status == CompletionStatus.NOT_DONE:
            action.status = ActionStatus.MISSED
            task.status = TaskStatus.MISSED
            task.miss_count += 1
            user = await session.get(User, action.user_id)
            if user is None:
                action.processing_at = None
                await session.commit()
                return

            policy = escalation_policy_for(user)
            goal = await session.get(Goal, task.goal_id)
            handler = handler_for(goal.domain if goal is not None else None, task.action_type)
            decision = None
            if handler is not None:
                outcome = await handler(
                    session,
                    action,
                    task,
                    user,
                    self.clock,
                    self.registry,
                    self.llm,
                    self.email_channel,
                )
                if outcome is not None:
                    decision = outcome.decision
                    apply_time = (
                        datetime.fromisoformat(decision.new_time)
                        if decision.new_time
                        else None
                    )
                    await apply_decision(session, action, self.registry, decision, apply_time)
                    policy = policy.model_copy(
                        update={"misses_before_escalate": outcome.escalation_threshold}
                    )

            if decision is None:
                await self._record_escalation(session, task, user, policy)
                result = await renegotiate(
                    session, action, user, self.clock, self.registry, self.llm
                )
                decision = result.decision
            else:
                await self._record_escalation(session, task, user, policy)

            await TextChannel(session).send(user, decision.message_to_user)
            if decision.action == "ask_user":
                session.add(
                    AgentSession(
                        user_id=user.id,
                        goal_id=task.goal_id,
                        scheduled_action_id=action.id,
                        status="awaiting_reply",
                        context={
                            "reason": decision.reason,
                            "message": decision.message_to_user,
                        },
                    )
                )
        elif status == CompletionStatus.UNKNOWN:
            action.status = ActionStatus.IN_PROGRESS
            session.add(
                Notification(
                    user_id=action.user_id,
                    channel="text",
                    title="Check-in",
                    body=f"Did you complete: {task.description}?",
                    level="info",
                )
            )
        action.processing_at = None
        logger.info(
            "monitor_action_processed",
            extra={
                "user_id": action.user_id,
                "goal_id": task.goal_id,
                "action_id": action.id,
            },
        )
        await session.commit()
