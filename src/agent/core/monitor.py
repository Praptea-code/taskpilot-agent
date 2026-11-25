from dataclasses import dataclass
from datetime import timedelta

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.config import get_settings
from agent.core.clock import Clock, SystemClock
from agent.db.session import get_sessionmaker
from agent.models import ActionStatus, ScheduledAction


@dataclass(frozen=True)
class MonitorConfig:
    grace_minutes: int = 10
    interval_seconds: int = 30


def sync_database_url(url: str) -> str:
    return url.replace("+aiosqlite", "").replace("+asyncpg", "").replace("+asyncmy", "")


async def scheduled_tick() -> None:
    settings = get_settings()
    monitor = Monitor(
        get_sessionmaker(settings.database_url),
        SystemClock(),
        MonitorConfig(grace_minutes=settings.grace_minutes),
    )
    await monitor.tick()


class Monitor:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        clock: Clock | None = None,
        config: MonitorConfig | None = None,
    ) -> None:
        self.maker = maker
        self.clock = clock or SystemClock()
        self.config = config or MonitorConfig()
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
            return list(result.scalars().all())
