from typing import Protocol, runtime_checkable

from agent.models import Notification, User


@runtime_checkable
class Channel(Protocol):
    name: str

    async def send(self, user: User, message: str) -> Notification: ...
