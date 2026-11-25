import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agent.llm.base import LLMClient

T = TypeVar("T", bound=BaseModel)


class LLMStructuredError(RuntimeError):
    pass


def extract_json(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = stripped.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")

    depth = 0
    for index in range(start, len(stripped)):
        char = stripped[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    raise ValueError("Unbalanced JSON object in response")


async def structured(
    llm: LLMClient,
    schema: type[T],
    system: str,
    user: str,
    retries: int = 3,
) -> T:
    schema_hint = json.dumps(schema.model_json_schema())
    system_prompt = f"{system}\n\nRespond with one JSON object matching this schema:\n{schema_hint}"
    current_user = user
    last_error = "unknown validation error"

    for _ in range(retries):
        raw = await llm.complete(system_prompt, current_user, json_mode=True)
        try:
            payload = extract_json(raw)
            return schema.model_validate(json.loads(payload))
        except (ValueError, ValidationError) as error:
            last_error = str(error)
            current_user = (
                f"{user}\n\nThe previous response was invalid: {last_error}\n"
                "Return valid JSON only."
            )

    raise LLMStructuredError(
        f"Could not produce valid {schema.__name__} after {retries} attempts: {last_error}"
    )
