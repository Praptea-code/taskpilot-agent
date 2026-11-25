from fastapi import Header, HTTPException

from agent.core.clock import Clock, SystemClock
from agent.executors.local_calendar import LocalCalendarExecutor
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm


async def get_current_user_id(x_user_id: str | None = Header(default=None)) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="X-User-Id header is required")
    try:
        return int(x_user_id)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid X-User-Id header") from error


def get_clock() -> Clock:
    return SystemClock()


def get_llm_client() -> LLMClient:
    return get_llm()


def get_registry() -> ExecutorRegistry:
    registry = ExecutorRegistry()
    executor = LocalCalendarExecutor()
    for action_type in ("focus", "general", "calendar"):
        registry.register(action_type, executor)
    return registry
