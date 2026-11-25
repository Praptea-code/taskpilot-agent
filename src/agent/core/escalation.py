from typing import TYPE_CHECKING, Any

from agent.schemas.escalation import (
    DEFAULT_ESCALATION_POLICY,
    EscalationDecision,
    EscalationPolicy,
)

if TYPE_CHECKING:
    from agent.models.task import Task
    from agent.models.user import User


def escalation_policy_for(user: "User") -> EscalationPolicy:
    override = user.escalation_policy or {}
    data: dict[str, Any] = DEFAULT_ESCALATION_POLICY.model_dump()
    if "misses_before_escalate" in override:
        data["misses_before_escalate"] = override["misses_before_escalate"]

    levels = {level["level"]: dict(level) for level in data["levels"]}
    for item in override.get("levels", []):
        number = item.get("level")
        if number is None:
            continue
        levels.setdefault(number, {"level": number})
        levels[number].update(item)
    data["levels"] = [levels[number] for number in sorted(levels)]
    return EscalationPolicy.model_validate(data)


def evaluate(task: "Task", policy: EscalationPolicy) -> EscalationDecision | None:
    if not policy.levels or task.miss_count < policy.misses_before_escalate:
        return None
    index = min(
        task.miss_count - policy.misses_before_escalate,
        len(policy.levels) - 1,
    )
    level = sorted(policy.levels, key=lambda item: item.level)[index]
    return EscalationDecision(
        level=level.level,
        channel=level.channel,
        tone=level.tone,
        notify_contacts=list(level.notify_contacts),
        reason=f"Missed {task.miss_count} times",
    )
