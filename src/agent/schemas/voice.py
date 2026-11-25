from typing import Literal

from pydantic import BaseModel


class VoiceResponse(BaseModel):
    text: str
    audio_base64: str
    audio_format: Literal["wav", "text"]
    kind: str
