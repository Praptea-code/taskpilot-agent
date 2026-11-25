from datetime import UTC, datetime

from agent.core.clock import Clock
from agent.core.prompts import CLASSIFY_REPLY_SYSTEM, with_context
from agent.llm.base import LLMClient
from agent.llm.structured import structured
from agent.models import User
from agent.schemas.llm import CheckInDecision


def parse_new_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def classify_checkin(
    text: str, user: User, clock: Clock, llm: LLMClient
) -> CheckInDecision:
    system = with_context(CLASSIFY_REPLY_SYSTEM, clock.now(), user.timezone)
    return await structured(llm, CheckInDecision, system, text)
