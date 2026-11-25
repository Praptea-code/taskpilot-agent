from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from agent.core.decomposer import DecomposedTask
from agent.executors.base import Slot
from agent.models import ActionStatus, ScheduledAction

STEP = timedelta(minutes=15)


@dataclass(frozen=True)
class SchedulingRequest:
    user_id: int
    tasks: list[DecomposedTask]
    deadline: datetime | None
    constraints: dict[str, object]
    user_timezone: str = "UTC"
    buffer_minutes: int = 10


@dataclass(frozen=True)
class SchedulingFailure:
    unscheduled: list[str]
    reason: str


@dataclass(frozen=True)
class ScheduleResult:
    actions: list[ScheduledAction] = field(default_factory=list)
    failure: SchedulingFailure | None = None


def parse_clock_time(value: object) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def carve(slots: list[Slot], busy: Slot) -> list[Slot]:
    result: list[Slot] = []
    for slot in slots:
        if busy.end <= slot.start or busy.start >= slot.end:
            result.append(slot)
            continue
        if busy.start > slot.start:
            result.append(Slot(slot.start, busy.start))
        if busy.end < slot.end:
            result.append(Slot(busy.end, slot.end))
    return result


def find_start(
    slots: list[Slot],
    duration: int,
    request: SchedulingRequest,
) -> datetime | None:
    zone = ZoneInfo(request.user_timezone)
    earliest = parse_clock_time(request.constraints.get("earliest_time"))
    latest = parse_clock_time(request.constraints.get("latest_time"))
    preferred = request.constraints.get("preferred_days")
    preferred_days = (
        {str(day).lower() for day in preferred} if isinstance(preferred, list) else set()
    )
    length = timedelta(minutes=duration)

    for slot in slots:
        cursor = slot.start
        while cursor + length <= slot.end:
            finish = cursor + length
            if request.deadline is not None and finish > request.deadline:
                break
            local_start = cursor.astimezone(zone)
            local_finish = finish.astimezone(zone)
            if preferred_days and local_start.strftime("%A").lower() not in preferred_days:
                cursor += STEP
                continue
            if earliest is not None and local_start.time() < earliest:
                cursor += STEP
                continue
            if latest is not None and local_finish.time() > latest:
                cursor += STEP
                continue
            return cursor
    return None


def schedule_tasks(slots: list[Slot], request: SchedulingRequest) -> ScheduleResult:
    available = list(slots)
    actions: list[ScheduledAction] = []
    unscheduled: list[str] = []

    for task in request.tasks:
        chosen = find_start(available, task.estimated_effort_minutes, request)
        if chosen is None:
            unscheduled.append(task.description)
            continue
        finish = chosen + timedelta(minutes=task.estimated_effort_minutes)
        actions.append(
            ScheduledAction(
                user_id=request.user_id,
                task_id=0,
                scheduled_at=chosen,
                duration_minutes=task.estimated_effort_minutes,
                status=ActionStatus.SCHEDULED,
                attempt_number=1,
            )
        )
        available = carve(
            available,
            Slot(chosen, finish + timedelta(minutes=request.buffer_minutes)),
        )

    failure = None
    if unscheduled:
        failure = SchedulingFailure(
            unscheduled=unscheduled,
            reason="No available slot fits these tasks before the deadline",
        )
    return ScheduleResult(actions=actions, failure=failure)
