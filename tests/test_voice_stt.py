import io
import wave

import pytest

from agent.channels.voice_channel import VoiceChannel


def make_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
    return buffer.getvalue()


async def test_transcribe_short_wav_when_extra_installed() -> None:
    pytest.importorskip("faster_whisper")

    text = await VoiceChannel("base.en").transcribe(make_wav())

    assert isinstance(text, str)
