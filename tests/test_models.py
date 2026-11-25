from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from agent.db.session import get_engine, get_sessionmaker
from agent.models import Base, Goal, ScheduledAction, Task, User


async def test_models_round_trip_with_relationships() -> None:
    url = "sqlite+aiosqlite:///:memory:"
    engine = get_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = get_sessionmaker(url)
    async with maker() as session:
        user = User(name="Ada", email="ada@example.com", timezone="UTC")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Plan a trip", domain="general")
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Book flights",
            action_type="calendar",
        )
        session.add(task)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            task_id=task.id,
            scheduled_at=datetime.now(UTC),
            duration_minutes=30,
            executor_name="local_calendar",
        )
        session.add(action)
        await session.commit()
        action_id = action.id

    query = (
        select(ScheduledAction)
        .where(ScheduledAction.id == action_id)
        .options(
            selectinload(ScheduledAction.task).selectinload(Task.goal).selectinload(Goal.user)
        )
    )
    async with maker() as session:
        loaded = (await session.execute(query)).scalar_one()
        assert loaded is not None
        assert loaded.task is not None
        assert loaded.task.goal is not None
        assert loaded.task.goal.user is not None
        assert loaded.task.goal.user.email == "ada@example.com"
        assert loaded.attempt_number == 1
