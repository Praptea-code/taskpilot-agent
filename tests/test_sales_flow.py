import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.channels.email_channel import EmailChannel
from agent.core.clock import FrozenClock
from agent.core.monitor import Monitor
from agent.core.service import GoalService
from agent.executors.email_executor import EmailExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    Base,
    InboxMessage,
    Lead,
    ScheduledAction,
    Task,
    User,
)

START = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
DEADLINE = datetime(2026, 1, 9, 23, 59, tzinfo=UTC)


def sales_responses() -> list[str]:
    tasks = [
        {
            "description": f"Follow up lead {number}",
            "estimated_effort_minutes": 15,
            "action_type": "send_email",
            "order": number,
        }
        for number in range(1, 21)
    ]
    return [
        json.dumps(
            {
                "title": "Follow up with 20 leads",
                "deadline": DEADLINE.isoformat(),
                "constraints": {
                    "earliest_time": "09:00",
                    "latest_time": "21:00",
                    "preferred_days": [],
                    "max_session_minutes": 60,
                    "notes": "",
                },
                "clarifying_question": None,
            }
        ),
        json.dumps({"tasks": tasks}),
    ]


async def test_sales_goal_uses_same_engine(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sales.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(name="User", email="user@example.com", timezone="UTC")
        session.add(user)
        await session.flush()
        for number in range(1, 21):
            session.add(
                Lead(
                    user_id=user.id,
                    name=f"Lead {number}",
                    email=f"lead{number}@example.com",
                    stage="new",
                )
            )
        await session.commit()

    sent: list[object] = []
    registry = ExecutorRegistry()
    registry.register("send_email", EmailExecutor(EmailChannel(console=True, sent=sent)))
    clock = FrozenClock(START)

    async with maker() as session:
        user_result = await session.execute(select(User))
        user = user_result.scalar_one()
        service = GoalService(session, registry, clock)
        outcome = await service.create_goal_plan(
            user,
            "Follow up with these 20 leads this week",
            "sales",
            llm=FakeLLMClient(sales_responses()),
        )
        assert outcome.schedule is not None
        assert outcome.goal.domain == "sales"

    async with maker() as session:
        actions = list((await session.execute(select(ScheduledAction))).scalars().all())
        tasks = list((await session.execute(select(Task))).scalars().all())
        assert len(actions) == 20
        assert len(tasks) == 20
        assert all(task.action_type == "send_email" for task in tasks)
        assert all(action.external_ref is not None for action in actions)
        lead_ids = sorted(int(task.payload["lead_id"]) for task in tasks)
        assert lead_ids == list(range(1, 21))
        for action in actions:
            task = await session.get(Task, action.task_id)
            assert task is not None
            session.add(
                InboxMessage(
                    user_id=action.user_id,
                    lead_id=task.payload["lead_id"],
                    subject="Re: intro",
                    body="Interested",
                    received_at=action.scheduled_at + timedelta(hours=1),
                )
            )
        await session.commit()

    clock.advance(timedelta(days=5))
    monitor = Monitor(maker, clock, registry=registry, llm=FakeLLMClient([]))

    await monitor.tick()

    async with maker() as session:
        actions = list((await session.execute(select(ScheduledAction))).scalars().all())
        tasks = list((await session.execute(select(Task))).scalars().all())
        assert all(action.status == ActionStatus.DONE for action in actions)
        assert all(task.status.value == "done" for task in tasks)
    assert len(sent) == 20
    await engine.dispose()
