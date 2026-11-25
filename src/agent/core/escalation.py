from typing import TYPE_CHECKING, Any

from agent.schemas.escalation import DEFAULT_ESCALATION_POLICY, EscalationPolicy

if TYPE_CHECKING:
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
