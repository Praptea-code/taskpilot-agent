import pytest
from pydantic import ValidationError

from agent.core.escalation import escalation_policy_for
from agent.models import User
from agent.schemas.escalation import DEFAULT_ESCALATION_POLICY, EscalationPolicy


def test_default_policy() -> None:
    policy = EscalationPolicy()

    assert policy.misses_before_escalate == 2
    assert policy.levels == DEFAULT_ESCALATION_POLICY.levels
    assert [level.level for level in policy.levels] == [1, 2]


def test_override_merges_defaults_by_level() -> None:
    user = User(
        name="User",
        email="user@example.com",
        escalation_policy={
            "misses_before_escalate": 3,
            "levels": [
                {"level": 1, "tone": "urgent"},
                {"level": 2, "notify_contacts": ["friend@example.com"]},
            ],
        },
    )

    policy = escalation_policy_for(user)

    assert policy.misses_before_escalate == 3
    assert policy.levels[0].model_dump() == {
        "level": 1,
        "channel": "text",
        "tone": "urgent",
        "notify_contacts": [],
    }
    assert policy.levels[1].channel == "text"
    assert policy.levels[1].tone == "urgent"
    assert policy.levels[1].notify_contacts == ["friend@example.com"]


def test_invalid_override_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EscalationPolicy.model_validate(
            {
                "misses_before_escalate": 0,
                "levels": [{"level": 1, "tone": "shouting"}],
            }
        )
