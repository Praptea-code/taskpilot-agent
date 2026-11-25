from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMCall:
    system: str
    user: str
    json_mode: bool
    temperature: float


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.2
    ) -> str: ...
