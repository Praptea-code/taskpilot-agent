from datetime import datetime

EXTRACT_GOAL_SYSTEM = (
    "You extract a clear goal from raw user text. "
    "Return only the requested JSON object.\n"
    "Example 1. Input: I need to finish my report by Friday, mornings only.\n"
    'Output: {"title": "Finish the report", "deadline": "by Friday", '
    '"constraints": {"earliest_time": "09:00", "latest_time": "12:00", '
    '"preferred_days": [], "max_session_minutes": 60, "notes": ""}, '
    '"clarifying_question": null}\n'
    "Example 2. Input: Prepare for the exam next week, ask me if the date is wrong.\n"
    'Output: {"title": "Prepare for the exam", "deadline": "next week", '
    '"constraints": {"earliest_time": null, "latest_time": null, '
    '"preferred_days": [], "max_session_minutes": null, "notes": ""}, '
    '"clarifying_question": "Which day next week?"}'
)

DECOMPOSE_GOAL_SYSTEM = (
    "You split a goal into ordered tasks with effort estimates. "
    "Return only the requested JSON object."
)

CLASSIFY_REPLY_SYSTEM = (
    "You classify a free text reply into one of the allowed outcomes. "
    "Allowed outcomes are completed, rescheduled, cancelled, and unclear. "
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
