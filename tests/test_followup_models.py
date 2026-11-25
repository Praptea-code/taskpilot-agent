from datetime import UTC, datetime

from sqlalchemy import select

from agent.db.session import get_engine, get_sessionmaker
from agent.models import (
    Base,
    CheckIn,
    EscalationEvent,
    Goal,
    Notification,
    ScheduledAction,
    Task,
    User,
)


async def test_remaining_models_round_trip() -> None:
    url = "sqlite+aiosqlite:///:memory:"
    engine = get_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = get_sessionmaker(url)
    now = datetime.now(UTC)
    async with maker() as session:
        user = User(name="Grace", email="grace@example.com", timezone="UTC")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Send the report")
        session.add(goal)
        await session.flush()
        task = Task(user_id=user.id, goal_id=goal.id, description="Send it", action_type="email")
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=now,
            duration_minutes=15,
        )
        session.add(action)
        await session.flush()

        check_in = CheckIn(
            user_id=user.id,
            scheduled_action_id=action.id,
            occurred_at=now,
            user_response_text="done",
            outcome="completed",
        )
        escalation = EscalationEvent(
            user_id=user.id,
            goal_id=goal.id,
            reason="missed twice",
            level=1,
            channel="text",
            occurred_at=now,
        )
        notification = Notification(
            user_id=user.id,
            channel="text",
            title="Check in",
            body="Did you finish?",
            level="info",
        )
        session.add_all([check_in, escalation, notification])
        await session.commit()
        check_in_id = check_in.id
        escalation_id = escalation.id
        notification_id = notification.id

    async with maker() as session:
        loaded_check_in = (
            await session.execute(select(CheckIn).where(CheckIn.id == check_in_id))
        ).scalar_one()
        loaded_escalation = (
            await session.execute(
                select(EscalationEvent).where(EscalationEvent.id == escalation_id)
            )
        ).scalar_one()
        loaded_notification = (
            await session.execute(select(Notification).where(Notification.id == notification_id))
        ).scalar_one()

        assert loaded_check_in.outcome == "completed"
        assert loaded_check_in.user_id == loaded_escalation.user_id
        assert loaded_escalation.level == 1
        assert loaded_notification.body == "Did you finish?"
        assert loaded_notification.read_at is None
