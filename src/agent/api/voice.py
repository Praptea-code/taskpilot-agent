import base64

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import (
    get_clock,
    get_current_user_id,
    get_llm_client,
    get_registry,
    get_voice_channel,
)
from agent.channels.voice_channel import VoiceChannel
from agent.core.clock import Clock
from agent.core.inbound import process_inbound
from agent.db.session import get_session
from agent.executors.registry import ExecutorRegistry
from agent.llm.base import LLMClient
from agent.schemas.channels import InboundMessage
from agent.schemas.voice import VoiceResponse

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("", response_model=VoiceResponse)
async def voice_message(
    audio: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
    registry: ExecutorRegistry = Depends(get_registry),
    clock: Clock = Depends(get_clock),
    voice: VoiceChannel = Depends(get_voice_channel),
) -> VoiceResponse:
    audio_bytes = await audio.read()
    transcript = await voice.transcribe(audio_bytes)
    message = InboundMessage(user_id=user_id, text=transcript, channel="voice")
    result = await process_inbound(session, message, clock, registry, llm)
    response_audio = await voice.synthesize(result.message)
    audio_format = "wav" if response_audio.startswith(b"RIFF") else "text"
    return VoiceResponse(
        text=result.message,
        audio_base64=base64.b64encode(response_audio).decode("ascii"),
        audio_format=audio_format,
        kind=result.kind,
    )
