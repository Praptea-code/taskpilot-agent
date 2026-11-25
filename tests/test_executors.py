from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent.executors.base import ActionExecutor, CompletionStatus, ExecutionResult, Slot
from agent.executors.registry import ExecutorRegistry
from agent.models import ScheduledAction, User


class DummyExecutor:
    name = "dummy"

    async def check_availability(
        self,
        user: User,
        start: datetime,
        end: datetime,
        session: AsyncSession | None = None,
    ) -> list[Slot]:
        return [Slot(start, end)]

    async def execute(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> ExecutionResult:
        return ExecutionResult(external_ref="dummy-ref")

    async def check_completion(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> CompletionStatus:
        return CompletionStatus.DONE

    async def cancel(
        self, action: ScheduledAction, session: AsyncSession | None = None
    ) -> None:
        return None

    async def reschedule(
        self,
        action: ScheduledAction,
        new_time: datetime,
        session: AsyncSession | None = None,
    ) -> None:
        return None


async def test_dummy_executor_implements_protocol() -> None:
    executor = DummyExecutor()
    assert isinstance(executor, ActionExecutor)


async def test_registry_register_and_get() -> None:
    registry = ExecutorRegistry()
    executor = DummyExecutor()
    registry.register("dummy_action", executor)

    assert registry.get("dummy_action") is executor
    assert list(registry.items()) == [("dummy_action", executor)]


async def test_registry_missing_action_type() -> None:
    registry = ExecutorRegistry()
    try:
        registry.get("missing")
    except KeyError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("Expected KeyError")
