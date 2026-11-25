from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.core.clock import FrozenClock
from agent.executors.base import CompletionStatus
from agent.executors.crm_executor import CRMExecutor
from agent.models import (
    ActionStatus,
    Base,
    Goal,
    Lead,
    ScheduledAction,
    Task,
    User,
)

NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


async def seed_task(maker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with maker() as session:
        user = User(name="User", email="user@example.com")
        session.add(user)
        await session.flush()
        goal = Goal(user_id=user.id, raw_input_text="Qualify leads", status="planned")
        session.add(goal)
        await session.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            description="Move lead to qualified",
            action_type="crm",
            payload={"lead_id": 1, "stage": "qualified", "note": "Spoke on phone"},
        )
        session.add(task)
        await session.flush()
        lead = Lead(
            user_id=user.id,
            name="Alice",
            email="alice@example.com",
            stage="new",
            notes="Imported",
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
        return {"lead": lead.id, "task": task.id, "action": action.id}


async def test_crm_execute_updates_lead_and_completion(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'crm.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await seed_task(maker)
    executor = CRMExecutor(FrozenClock(NOW))

    async with maker() as session:
        action = await session.get(ScheduledAction, ids["action"])
        assert action is not None
        assert await executor.check_completion(action, session) == CompletionStatus.NOT_DONE
        result = await executor.execute(action, session)
        lead = await session.get(Lead, ids["lead"])
        assert result.external_ref == f"lead-{ids['lead']}-qualified"
        assert action.external_ref == result.external_ref
        assert lead is not None and lead.stage == "qualified"
        assert lead.notes == "Imported\nSpoke on phone"
        assert lead.last_contacted_at is not None
        assert lead.last_contacted_at.replace(tzinfo=UTC) == NOW
        assert await executor.check_completion(action, session) == CompletionStatus.DONE

    async with maker() as session:
        task = await session.get(Task, ids["task"])
        action = await session.get(ScheduledAction, ids["action"])
        assert task is not None and action is not None
        task.payload = {"lead_id": ids["lead"], "stage": "won"}
        await session.commit()
        assert await executor.check_completion(action, session) == CompletionStatus.NOT_DONE
    await engine.dispose()
