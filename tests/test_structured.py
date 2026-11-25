import pytest
from pydantic import BaseModel

from agent.llm import FakeLLMClient
from agent.llm.structured import LLMStructuredError, structured


class Answer(BaseModel):
    answer: str
    count: int


async def test_structured_valid_json() -> None:
    llm = FakeLLMClient(['{"answer": "yes", "count": 2}'])
    result = await structured(llm, Answer, "system", "user")
    assert result.answer == "yes"
    assert result.count == 2


async def test_structured_fenced_json() -> None:
    llm = FakeLLMClient(['Here it is:\n```json\n{"answer": "ok", "count": 1}\n```\nThanks.'])
    result = await structured(llm, Answer, "system", "user")
    assert result.count == 1


async def test_structured_retry_feeds_validation_error() -> None:
    llm = FakeLLMClient(['{"answer": "bad"}', '{"answer": "good", "count": 3}'])
    result = await structured(llm, Answer, "system", "user")
    assert result.answer == "good"
    assert len(llm.calls) == 2
    assert "count" in llm.calls[1].user
    assert "invalid" in llm.calls[1].user


async def test_structured_raises_after_retries() -> None:
    llm = FakeLLMClient(["not json", "still not json", "no"])
    with pytest.raises(LLMStructuredError, match="after 3 attempts"):
        await structured(llm, Answer, "system", "user", retries=3)
    assert len(llm.calls) == 3
