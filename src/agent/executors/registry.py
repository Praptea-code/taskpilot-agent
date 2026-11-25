from collections.abc import Iterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.executors.base import ActionExecutor


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, ActionExecutor] = {}

    def register(self, action_type: str, executor: ActionExecutor) -> None:
        self._executors[action_type] = executor

    def get(self, action_type: str) -> ActionExecutor:
        if action_type not in self._executors:
            raise KeyError(f"No executor registered for action type: {action_type}")
        return self._executors[action_type]

    def items(self) -> Iterator[tuple[str, ActionExecutor]]:
        return iter(self._executors.items())


_registry = ExecutorRegistry()


def get_registry() -> ExecutorRegistry:
    return _registry


def build_default_registry(
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> ExecutorRegistry:
    from agent.executors.local_calendar import LocalCalendarExecutor

    registry = ExecutorRegistry()
    executor = LocalCalendarExecutor(maker)
    for action_type in ("focus", "general", "calendar"):
        registry.register(action_type, executor)
    return registry
