from fastapi import Header, HTTPException

from agent.channels.voice_channel import VoiceChannel
from agent.core.clock import Clock, SystemClock
from agent.executors.registry import ExecutorRegistry, build_default_registry
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
    return build_default_registry()


def get_voice_channel() -> VoiceChannel:
    return VoiceChannel()
