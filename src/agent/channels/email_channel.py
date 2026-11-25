from dataclasses import dataclass

import aiosmtplib

from agent.config import get_settings
from agent.models import User


@dataclass(frozen=True)
class OutboundEmail:
    recipient: str
    subject: str
    body: str


class EmailChannel:
    name = "email"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        console: bool | None = None,
        sender: str | None = None,
        sent: list[OutboundEmail] | None = None,
    ) -> None:
        settings = get_settings()
        self.host = host or settings.smtp_host
        self.port = port or settings.smtp_port
        self.console = settings.smtp_console if console is None else console
        self.sender = sender or settings.smtp_sender
        self.username = settings.smtp_user
        self.password = settings.smtp_password
        self.sent = sent if sent is not None else []

    async def send(
        self,
        user: User,
        message: str,
        *,
        to: str | None = None,
        subject: str = "TaskPilot escalation",
    ) -> None:
        recipient = to or user.email
        email = OutboundEmail(recipient=recipient, subject=subject, body=message)
        if self.console:
            self.sent.append(email)
            return

        content = (
            f"From: {self.sender}\n"
            f"To: {recipient}\n"
            f"Subject: {subject}\n"
            f"\n{message}"
        )
        options: dict[str, object] = {
            "hostname": self.host,
            "port": self.port,
        }
        if self.username and self.password:
            options["username"] = self.username
            options["password"] = self.password
        await aiosmtplib.send(content, **options)
