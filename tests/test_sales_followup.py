from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.channels.email_channel import EmailChannel
from agent.core.clock import FrozenClock
from agent.core.monitor import Monitor
from agent.executors.email_executor import EmailExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    Base,
    EscalationEvent,
    Goal,
    Lead,
    Notification,
    ScheduledAction,
    Task,
    User,
)

START = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


async def test_no_reply_followup_renegotiation(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'followup.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(name="User", email="user@example.com", timezone="UTC")
        session.add(user)
        await session.flush()
        goal = Goal(
            user_id=user.id,
            raw_input_text="Follow up with the lead",
            extracted_goal="Follow up with the lead",
            deadline=START + timedelta(days=7),
            constraints={
                "earliest_time": "00:00",
                "latest_time": "23:59",
                "preferred_days": [],
                "max_session_minutes": 60,
            },
            status="planned",
            domain="sales",
        )
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Follow up lead 1",
            action_type="send_email",
            estimated_effort_minutes=15,
            payload={"lead_id": 1, "template": "intro", "step": 1},
            status="scheduled",
        )
        session.add(task)
        await session.flush()
        lead = Lead(
            user_id=user.id,
            name="Alice",
            email="alice@example.com",
            company="Acme",
            stage="new",
        )
        session.add(lead)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=START - timedelta(minutes=11),
            duration_minutes=15,
            status=ActionStatus.SCHEDULED,
        )
        session.add(action)
        await session.commit()
        ids = {"user": user.id, "goal": goal.id, "task": task.id, "action": action.id}

    email_channel = EmailChannel(console=True)
    executor = EmailExecutor(email_channel, FrozenClock(START))
    registry = ExecutorRegistry()
    registry.register("send_email", executor)
    clock = FrozenClock(START)
    monitor = Monitor(
        maker,
        clock,
        registry=registry,
        llm=FakeLLMClient(
            [
                "First follow-up draft",
                "Second follow-up draft",
                "Third follow-up draft",
                "Level 1 escalation text",
            ]
        ),
        email_channel=email_channel,
    )

    await monitor.tick()
    async with maker() as session:
        task = await session.get(Task, ids["task"])
        events = list((await session.execute(select(EscalationEvent))).scalars().all())
        assert task is not None and task.miss_count == 1
        assert events == []
        assert len(email_channel.sent) == 1
        assert email_channel.sent[0].body == "First follow-up draft"

    clock.advance(timedelta(hours=25))
    await monitor.tick()
    async with maker() as session:
        task = await session.get(Task, ids["task"])
        events = list((await session.execute(select(EscalationEvent))).scalars().all())
        assert task is not None and task.miss_count == 2
        assert events == []
        assert len(email_channel.sent) == 2
        assert email_channel.sent[1].body == "Second follow-up draft"

    clock.advance(timedelta(hours=25))
    await monitor.tick()
    async with maker() as session:
        task = await session.get(Task, ids["task"])
        events = list((await session.execute(select(EscalationEvent))).scalars().all())
        notifications = list(
            (
                await session.execute(
                    select(Notification).where(Notification.user_id == ids["user"])
                )
            )
            .scalars()
            .all()
        )
        assert task is not None and task.miss_count == 3
        assert [event.level for event in events] == [1]
        assert any(item.body == "Level 1 escalation text" for item in notifications)
        assert len(email_channel.sent) == 3
        assert email_channel.sent[2].body == "Third follow-up draft"
    await engine.dispose()
