import asyncio
import tempfile

from agent.config import get_settings


class VoiceChannel:
    name = "voice"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or get_settings().whisper_model
        self._model: object | None = None

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "Install the voice extra with python -m pip install -e '.[voice]'"
            ) from error
        self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        return self._model

    def _transcribe(self, audio_bytes: bytes) -> str:
        model = self._load_model()
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            handle.write(audio_bytes)
            handle.flush()
            segments, _ = model.transcribe(handle.name)
            text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()

    async def transcribe(self, audio_bytes: bytes) -> str:
        return await asyncio.to_thread(self._transcribe, audio_bytes)
