from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from agent.core.clock import Clock
from agent.core.prompts import EXTRACT_GOAL_SYSTEM, with_context
from agent.llm.base import LLMClient
from agent.llm.structured import structured
from agent.models import User
from agent.schemas.llm import ExtractedGoal

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class GoalExtraction:
    title: str
    deadline: datetime | None
    constraints: dict[str, object]
    clarifying_question: str | None


def resolve_deadline(value: str | None, clock: Clock, user_timezone: str) -> datetime | None:
    if not value:
        return None

    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(user_timezone))
        return parsed.astimezone(UTC)

    local_zone = ZoneInfo(user_timezone)
    local_today = clock.now().astimezone(local_zone).date()
    lowered = text.lower()

    if "tomorrow" in lowered:
        target = local_today + timedelta(days=1)
    elif "today" in lowered:
        target = local_today
    elif "end of week" in lowered:
        target = local_today + timedelta(days=4 - local_today.weekday())
    else:
        target = None
        for name, index in _WEEKDAYS.items():
            if name in lowered:
                days_ahead = (index - local_today.weekday()) % 7
                if "next" in lowered and days_ahead == 0:
                    days_ahead = 7
                target = local_today + timedelta(days=days_ahead)
                break
        if target is None:
            return None

    local_end = datetime(target.year, target.month, target.day, 23, 59, tzinfo=local_zone)
    return local_end.astimezone(UTC)


async def extract_goal(raw: str, user: User, clock: Clock, llm: LLMClient) -> GoalExtraction:
    system = with_context(EXTRACT_GOAL_SYSTEM, clock.now(), user.timezone)
    extracted = await structured(llm, ExtractedGoal, system, raw)
    return GoalExtraction(
        title=extracted.title,
        deadline=resolve_deadline(extracted.deadline, clock, user.timezone),
        constraints=extracted.constraints.model_dump(),
        clarifying_question=extracted.clarifying_question,
    )
