import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from agent.channels.email_channel import EmailChannel
from agent.config import Settings, get_settings
from agent.core.clock import Clock, FrozenClock
from agent.core.monitor import Monitor
from agent.core.service import GoalService
from agent.db.session import get_engine, get_sessionmaker
from agent.executors.email_executor import EmailExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    Base,
    InboxMessage,
    Lead,
    ScheduledAction,
    User,
)

DEMO_EMAIL = "sales-demo@example.com"
START = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an offline sales follow-up demo")
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use canned offline responses instead of the configured LLM",
    )
    return parser


def canned_responses(lead_ids: list[int]) -> list[str]:
    tasks = [
        {
            "description": f"Follow up lead {lead_id}",
            "estimated_effort_minutes": 15,
            "action_type": "send_email",
            "order": number,
        }
        for number, lead_id in enumerate(lead_ids, start=1)
    ]
    return [
        json.dumps(
            {
                "title": f"Follow up with {len(lead_ids)} leads",
                "deadline": "2026-01-09T23:59:00Z",
                "constraints": {
                    "earliest_time": "00:00",
                    "latest_time": "23:59",
                    "preferred_days": [],
                    "max_session_minutes": 60,
                    "notes": "",
                },
                "clarifying_question": None,
            }
        ),
        json.dumps({"tasks": tasks}),
    ]


def build_llm(settings: Settings, lead_ids: list[int]) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient(canned_responses(lead_ids))
    return get_llm(settings)


async def ensure_leads(session, user: User) -> list[Lead]:
    result = await session.execute(select(Lead).where(Lead.user_id == user.id))
    leads = list(result.scalars().all())
    if leads:
        return sorted(leads, key=lambda item: item.id)
    for number in range(1, 6):
        session.add(
            Lead(
                user_id=user.id,
                name=f"Lead {number}",
                email=f"lead{number}@example.com",
                company=f"Company {number}",
                stage="new",
                notes="Seeded for the sales demo",
            )
        )
    await session.commit()
    result = await session.execute(select(Lead).where(Lead.user_id == user.id))
    return sorted(result.scalars().all(), key=lambda item: item.id)


async def run_demo(settings: Settings, use_fake: bool) -> int:
    engine = get_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = get_sessionmaker(settings.database_url)

    if use_fake:
        settings = settings.model_copy(update={"llm_provider": "fake"})

    channel = EmailChannel()
    clock: Clock = FrozenClock(START)
    executor = EmailExecutor(channel, clock)
    registry = ExecutorRegistry()
    registry.register("send_email", executor)

    async with maker() as session:
        result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                name="Sales Demo User",
                email=DEMO_EMAIL,
                timezone=settings.timezone,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        leads = await ensure_leads(session, user)
        llm = build_llm(settings, [lead.id for lead in leads])
        service = GoalService(session, registry, clock)
        outcome = await service.create_goal_plan(
            user,
            f"Follow up with these {len(leads)} leads this week",
            "sales",
            llm,
        )

        if outcome.clarifying_question:
            print(f"Need more detail: {outcome.clarifying_question}")
            return 0

        print(f"Goal: {outcome.goal.extracted_goal}")
        print(f"Status: {outcome.goal.status.value}")
        if outcome.schedule is None or not outcome.schedule.actions:
            print("No actions were scheduled")
            if outcome.schedule is not None and outcome.schedule.failure is not None:
                print(f"Reason: {outcome.schedule.failure.reason}")
            return 0

        zone = ZoneInfo(user.timezone)
        actions = list(
            (
                await session.execute(
                    select(ScheduledAction)
                    .where(ScheduledAction.user_id == user.id)
                    .order_by(ScheduledAction.scheduled_at)
                )
            )
            .scalars()
            .all()
        )
        print("Emails sent to the console backend:")
        for email in channel.sent:
            print(f"To: {email.recipient} | Subject: {email.subject}")
            print(f"  {email.body}")
        print("Scheduled follow-ups:")
        for number, action in enumerate(actions, start=1):
            local_time = action.scheduled_at.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")
            print(f"{number}. {local_time} | {action.external_ref}")
            session.add(
                InboxMessage(
                    user_id=user.id,
                    lead_id=leads[number - 1].id,
                    subject="Re: intro",
                    body="Sounds good",
                    received_at=action.scheduled_at + timedelta(hours=1),
                )
            )
        await session.commit()

    clock.advance(timedelta(days=5))
    monitor = Monitor(maker, clock, registry=registry, llm=FakeLLMClient([]))
    await monitor.tick()

    async with maker() as session:
        demo_user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        remaining = list(
            (
                await session.execute(
                    select(ScheduledAction).where(
                        ScheduledAction.user_id == demo_user.id,
                        ScheduledAction.status != ActionStatus.DONE,
                    )
                )
            )
            .scalars()
            .all()
        )
        print(f"Actions still open after simulated replies: {len(remaining)}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()
    return asyncio.run(run_demo(settings, args.fake))


if __name__ == "__main__":
    if os.environ.get("LLM_PROVIDER") == "fake":
        get_settings.cache_clear()
    raise SystemExit(main())
