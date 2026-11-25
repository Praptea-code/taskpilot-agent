import logging

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from agent.channels.text_channel import TextChannel
from agent.models import Notification, User


async def test_text_channel_persists_and_logs_notification(
    client: tuple[httpx.AsyncClient, async_sessionmaker], caplog
) -> None:
    api, maker = client
    with caplog.at_level(logging.INFO):
        async with maker() as session:
            user = await session.get(User, 1)
            assert user is not None
            await TextChannel(session).send(user, "Time to start")
            await session.commit()

    assert "notification created" in caplog.text
    result = await api.get("/notifications", headers={"X-User-Id": "1"})
    assert result.status_code == 200
    body = result.json()
    assert len(body) == 1
    assert body[0]["body"] == "Time to start"
    assert body[0]["channel"] == "text"


async def test_mark_notification_read_is_tenant_scoped(
    client: tuple[httpx.AsyncClient, async_sessionmaker]
) -> None:
    api, maker = client
    async with maker() as session:
        notification = Notification(
            user_id=1,
            channel="text",
            title="Reminder",
            body="Start now",
            level="info",
        )
        session.add(notification)
        await session.commit()
        notification_id = notification.id

    result = await api.post(
        f"/notifications/{notification_id}/read", headers={"X-User-Id": "1"}
    )
    assert result.status_code == 200
    assert result.json()["read_at"] is not None

    other = await api.post(
        f"/notifications/{notification_id}/read", headers={"X-User-Id": "2"}
    )
    assert other.status_code == 404
