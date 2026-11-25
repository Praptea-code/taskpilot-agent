import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.channels.email_channel import EmailChannel
from agent.core.clock import FrozenClock
from agent.core.monitor import Monitor
from agent.executors.base import CompletionStatus, Slot
from agent.executors.registry import ExecutorRegistry
from agent.llm.fake import FakeLLMClient
from agent.models import (
    ActionStatus,
    Base,
    EscalationEvent,
    Goal,
    Notification,
    ScheduledAction,
    Task,
    TaskStatus,
    User,
)

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class MissExecutor:
    name = "focus"

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        return CompletionStatus.NOT_DONE

    async def check_availability(
        self, user, start, end, session=None
    ) -> list[Slot]:
        return [Slot(start + timedelta(hours=1), start + timedelta(hours=3))]

    async def reschedule(
        self, action: ScheduledAction, new_time: datetime, session=None
    ) -> None:
        return None

    async def cancel(self, action: ScheduledAction, session=None) -> None:
        return None


def decision(action: str, new_time: datetime | None, message: str) -> str:
    return json.dumps(
        {
            "action": action,
            "new_time": new_time.isoformat() if new_time else None,
            "reason": "Scenario step",
            "message_to_user": message,
        }
    )


async def test_end_to_end_escalation_scenario(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scenario.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        user = User(
            name="User",
            email="user@example.com",
            escalation_policy={
                "levels": [
                    {
                        "level": 2,
                        "notify_contacts": ["friend@example.com"],
                    }
                ]
            },
        )
        session.add(user)
        await session.flush()
        goal = Goal(
            user_id=user.id,
            raw_input_text="Goal",
            status="planned",
            deadline=START + timedelta(days=2),
            constraints={
                "earliest_time": "00:00",
                "latest_time": "23:59",
                "preferred_days": [],
                "max_session_minutes": 60,
            },
        )
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Task",
            action_type="focus",
            estimated_effort_minutes=30,
            status=TaskStatus.SCHEDULED,
        )
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=START - timedelta(minutes=11),
            duration_minutes=30,
            status=ActionStatus.SCHEDULED,
        )
        session.add(action)
        await session.commit()
        ids = {"user": user.id, "task": task.id, "action": action.id}

    registry = ExecutorRegistry()
    registry.register("focus", MissExecutor())
    clock = FrozenClock(START)
    sent: list[object] = []
    monitor = Monitor(
        maker,
        clock,
        registry=registry,
        llm=FakeLLMClient(
            [
                decision("reschedule", START + timedelta(hours=1), "Moved to 13:00"),
                "Level 1 text",
                decision("reschedule", START + timedelta(hours=3), "Moved to 15:00"),
                "Level 2 text",
                decision("keep_as_is", None, "Keeping the plan"),
            ]
        ),
        email_channel=EmailChannel(console=True, sent=sent),
    )

    await monitor.tick()
    async with maker() as session:
        task = await session.get(Task, ids["task"])
        action = await session.get(ScheduledAction, ids["action"])
        events = list(
            (await session.execute(select(EscalationEvent))).scalars().all()
        )
        assert task is not None and task.miss_count == 1
        assert action is not None and action.status == ActionStatus.SCHEDULED
        assert action.scheduled_at.replace(tzinfo=UTC) == START + timedelta(hours=1)
        assert events == []

    clock.advance(timedelta(hours=2))
    await monitor.tick()
    async with maker() as session:
        task = await session.get(Task, ids["task"])
        events = list(
            (await session.execute(select(EscalationEvent))).scalars().all()
        )
        notifications = list(
            (
                await session.execute(
                    select(Notification).where(Notification.user_id == ids["user"])
                )
            )
            .scalars()
            .all()
        )
        assert task is not None and task.miss_count == 2
        assert [event.level for event in events] == [1]
        assert any(item.body == "Level 1 text" for item in notifications)
        assert sent == []

    clock.advance(timedelta(hours=2))
    await monitor.tick()
    async with maker() as session:
        task = await session.get(Task, ids["task"])
        events = list(
            (await session.execute(select(EscalationEvent))).scalars().all()
        )
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
        assert [event.level for event in events] == [1, 2]
        assert any(item.body == "Level 2 text" for item in notifications)
        assert len(sent) == 1
        email = sent[0]
        assert email.recipient == "friend@example.com"
        assert email.body == "Level 2 text"
    await engine.dispose()
