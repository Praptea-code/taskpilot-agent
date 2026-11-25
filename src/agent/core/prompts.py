from datetime import datetime

EXTRACT_GOAL_SYSTEM = (
    "You extract a clear goal from raw user text. "
    "Return only the requested JSON object."
)

DECOMPOSE_GOAL_SYSTEM = (
    "You split a goal into ordered tasks with effort estimates. "
    "Return only the requested JSON object."
)

CLASSIFY_REPLY_SYSTEM = (
    "You classify a free text reply into one of the allowed outcomes. "
    "Return only the requested JSON object."
)

RENEGOTIATE_SYSTEM = (
    "You decide how to handle a missed scheduled action. "
    "Return only the requested JSON object."
)

ESCALATION_SYSTEM = (
    "You write a short message matching the requested tone. "
    "Return only the requested JSON object."
)


def with_context(template: str, now: datetime, user_timezone: str) -> str:
    return (
        f"{template}\n"
        f"Current UTC time: {now.isoformat()}\n"
        f"User timezone: {user_timezone}"
    )
