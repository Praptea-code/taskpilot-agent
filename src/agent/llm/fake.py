from collections import deque
from collections.abc import Sequence

from agent.llm.base import LLMCall


class FakeLLMClient:
    def __init__(self, responses: Sequence[str] | None = None) -> None:
        self._responses = deque(responses or [])
        self.calls: list[LLMCall] = []

    async def complete(
        self, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.2
    ) -> str:
        self.calls.append(LLMCall(system, user, json_mode, temperature))
        if not self._responses:
            raise RuntimeError("FakeLLMClient has no scripted responses left")
        return self._responses.popleft()
