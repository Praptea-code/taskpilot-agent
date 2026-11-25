from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.channels.email_channel import EmailChannel
from agent.core.clock import FrozenClock
from agent.executors.base import CompletionStatus
from agent.executors.email_executor import EmailExecutor
from agent.models import (
    ActionStatus,
    Base,
    Goal,
    InboxMessage,
    Lead,
    ScheduledAction,
    Task,
    User,
)

NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


async def seed_lead(
    maker: async_sessionmaker[AsyncSession], *, last_contacted_at: datetime | None = None
) -> dict[str, int]:
    async with maker() as session:
        user = User(name="User", email="user@example.com")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Follow up", status="planned")
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Send intro",
            action_type="send_email",
            payload={"lead_id": 1, "template": "intro", "step": 1},
        )
        session.add(task)
        await session.flush()
        task_id = task.id
        lead = Lead(
            user_id=user.id,
            name="Alice",
            email="alice@example.com",
            stage="new",
            last_contacted_at=last_contacted_at,
        )
        session.add(lead)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=NOW,
            duration_minutes=5,
            status=ActionStatus.SCHEDULED,
        )
        session.add(action)
        await session.commit()
        return {"user": user.id, "lead": lead.id, "task": task_id, "action": action.id}


async def test_execute_sends_console_email_and_sets_ref(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'execute.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await seed_lead(maker)
    sent: list[object] = []
    executor = EmailExecutor(EmailChannel(console=True, sent=sent), FrozenClock(NOW))

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        assert action is not None
        result = await executor.execute(action, session)
        lead = await session.get(Lead, ids["lead"])
        assert result.external_ref is not None
        assert action.external_ref == result.external_ref
        assert lead is not None and lead.last_contacted_at is not None
        assert lead.last_contacted_at.replace(tzinfo=UTC) == NOW
        assert len(sent) == 1
        email = sent[0]
        assert email.recipient == "alice@example.com"
        assert email.body == "Template: intro\nStep: 1"
    await engine.dispose()


async def test_check_availability_respects_cadence_and_weekends(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'slots.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await seed_lead(maker, last_contacted_at=datetime(2026, 1, 2, tzinfo=UTC))
    executor = EmailExecutor(EmailChannel(console=True), FrozenClock(NOW))

    async with maker() as session:
        user = await session.get(User, 1)
        assert user is not None
        early = await executor.check_availability(
            user, datetime(2026, 1, 3, tzinfo=UTC), datetime(2026, 1, 4, tzinfo=UTC), session
        )
        assert early == []
        slots = await executor.check_availability(
            user,
            datetime(2026, 1, 3, tzinfo=UTC),
            datetime(2026, 1, 10, tzinfo=UTC),
            session,
        )
        assert len(slots) == 5
        assert slots[0].start.weekday() == 0
        assert slots[0].start.hour == 9
        assert all(slot.start.weekday() < 5 for slot in slots)
    await engine.dispose()


async def test_check_completion_reads_local_inbox(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'inbox.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await seed_lead(maker)
    executor = EmailExecutor(EmailChannel(console=True), FrozenClock(NOW))

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        assert action is not None
        assert await executor.check_completion(action, session) == CompletionStatus.NOT_DONE

    async with maker() as session:
        session.add(
            InboxMessage(
                user_id=ids["user"],
                lead_id=ids["lead"],
                subject="Re: intro",
                body="Sounds good",
                received_at=NOW + timedelta(minutes=5),
            )
        )
        await session.commit()

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        lead = await session.get(Lead, ids["lead"])
        assert action is not None
        assert await executor.check_completion(action, session) == CompletionStatus.DONE
        assert lead is not None and lead.replied_at is not None
        assert lead.replied_at.replace(tzinfo=UTC) == NOW + timedelta(minutes=5)
    await engine.dispose()
