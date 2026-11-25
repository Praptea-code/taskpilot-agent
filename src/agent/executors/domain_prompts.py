import re
from collections.abc import Callable
from dataclasses import dataclass, field

PayloadBuilder = Callable[[int, str], dict[str, object]]
Handler = Callable[..., object]


@dataclass(frozen=True)
class DomainHints:
    examples: str = ""
    payloads: dict[tuple[str, str], PayloadBuilder] = field(default_factory=dict)


_SALES_EXAMPLES = (
    "Example: follow up with these 20 leads this week.\n"
    "Decompose into one send_email task per lead with action_type send_email.\n"
    "Describe each task as Follow up lead N so the payload can identify the lead."
)


def _sales_payload(order: int, description: str) -> dict[str, object]:
    match = re.search(r"lead\s+(\d+)", description, flags=re.IGNORECASE)
    return {
        "lead_id": int(match.group(1)) if match else 1,
        "template": "intro",
        "step": order,
    }


_HINTS = {
    "sales": DomainHints(
        examples=_SALES_EXAMPLES,
        payloads={("sales", "send_email"): _sales_payload},
    )
}

_HANDLERS: dict[tuple[str, str], Handler] = {}


def register_domain_hints(domain: str, hints: DomainHints) -> None:
    _HINTS[domain] = hints


def hints_for_domain(domain: str | None) -> DomainHints:
    return _HINTS.get(domain or "general", DomainHints())


def payload_for_action(
    domain: str | None, action_type: str, order: int, description: str
) -> dict[str, object]:
    builder = hints_for_domain(domain).payloads.get((domain or "", action_type))
    if builder is None:
        return {"order": order}
    return builder(order, description)


def handler_for(domain: str | None, action_type: str) -> Handler | None:
    key = (domain or "", action_type)
    if key not in _HANDLERS and key == ("sales", "send_email"):
        from agent.executors.sales_followup import handle_no_reply

        _HANDLERS[key] = handle_no_reply
    return _HANDLERS.get(key)
