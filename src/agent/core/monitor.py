from dataclasses import dataclass
from datetime import timedelta

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.channels.text_channel import TextChannel
from agent.config import get_settings
from agent.core.clock import Clock, SystemClock
from agent.core.escalation import escalation_policy_for, evaluate
from agent.core.renegotiator import renegotiate
from agent.core.state import finish_goal_if_done
from agent.db.session import get_sessionmaker
from agent.executors.base import CompletionStatus
from agent.executors.registry import ExecutorRegistry, build_default_registry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm
from agent.models import (
    ActionStatus,
    AgentSession,
    EscalationEvent,
    Notification,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)


@dataclass(frozen=True)
class MonitorConfig:
    grace_minutes: int = 10
    interval_seconds: int = 30


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
    ) -> None:
        self.maker = maker
        self.clock = clock or SystemClock()
        self.config = config or MonitorConfig()
        self.registry = registry or ExecutorRegistry()
        self.llm = llm or get_llm()
        self.scheduler = AsyncIOScheduler()

    async def start(self, jobstore_url: str) -> None:
        if self.scheduler.running:
            return
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
        cutoff = self.clock.now() - timedelta(minutes=self.config.grace_minutes)
        async with self.maker() as session:
            result = await session.execute(
                select(ScheduledAction)
                .where(
                    ScheduledAction.status == ActionStatus.SCHEDULED,
                    ScheduledAction.scheduled_at <= cutoff,
                )
                .order_by(ScheduledAction.id)
            )
            due = list(result.scalars().all())
            for action in due:
                await self.process(session, action)
            return due

    async def process(self, session: AsyncSession, action: ScheduledAction) -> None:
        task = await session.get(Task, action.task_id)
        if task is None:
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
                await session.commit()
                return
            escalation = evaluate(task, escalation_policy_for(user))
            if escalation is not None:
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
            result = await renegotiate(
                session, action, user, self.clock, self.registry, self.llm
            )
            await TextChannel(session).send(user, result.decision.message_to_user)
            if result.decision.action == "ask_user":
                session.add(
                    AgentSession(
                        user_id=user.id,
                        goal_id=task.goal_id,
                        scheduled_action_id=action.id,
                        status="awaiting_reply",
                        context={
                            "reason": result.decision.reason,
                            "message": result.decision.message_to_user,
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
        await session.commit()
