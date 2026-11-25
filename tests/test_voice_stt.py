import io
import os
import shutil
import wave
from types import SimpleNamespace

import pytest

from agent.channels import voice_channel
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


@pytest.mark.skipif(
    shutil.which("piper") is None or not os.environ.get("PIPER_MODEL"),
    reason="Piper voice is not installed",
)
async def test_synthesize_with_piper_when_installed() -> None:
    audio = await VoiceChannel().synthesize("Hello from the demo")

    assert audio.startswith(b"RIFF")


async def test_synthesize_falls_back_to_text(monkeypatch) -> None:
    monkeypatch.setattr(
        voice_channel,
        "get_settings",
        lambda: SimpleNamespace(whisper_model="base.en", piper_model=""),
    )

    result = await VoiceChannel().synthesize("Hello from the demo")

    assert result == b"Hello from the demo"
