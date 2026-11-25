import logging

from sqlalchemy.ext.asyncio import AsyncSession

from agent.models import Notification, User

logger = logging.getLogger(__name__)


class TextChannel:
    name = "text"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def send(self, user: User, message: str) -> Notification:
        notification = Notification(
            user_id=user.id,
            channel=self.name,
            title="Agent message",
            body=message,
            level="info",
        )
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        logger.info("notification created id=%s user_id=%s", notification.id, user.id)
        return notification
