from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.auth import user_id_for_api_key
from agent.channels.voice_channel import VoiceChannel
from agent.config import get_settings
from agent.core.clock import Clock, SystemClock
from agent.db.session import get_session
from agent.executors.registry import ExecutorRegistry, build_default_registry
from agent.llm.base import LLMClient
from agent.llm.factory import get_llm


async def get_current_user_id(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> int:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Invalid API key")
        user_id = await user_id_for_api_key(session, token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user_id
    if x_user_id is not None and get_settings().dev_mode:
        try:
            return int(x_user_id)
        except ValueError as error:
            raise HTTPException(status_code=401, detail="Invalid X-User-Id header") from error
    raise HTTPException(status_code=401, detail="API key required")


def get_clock() -> Clock:
    return SystemClock()


def get_llm_client() -> LLMClient:
    return get_llm()


def get_registry() -> ExecutorRegistry:
    return build_default_registry()


def get_voice_channel() -> VoiceChannel:
    return VoiceChannel()
