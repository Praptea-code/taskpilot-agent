import pytest

from agent.config import Settings
from agent.llm import FakeLLMClient, get_llm


async def test_fake_llm_scripting_records_calls() -> None:
    llm = FakeLLMClient(["first", "second"])

    assert await llm.complete("system", "one") == "first"
    assert await llm.complete("system", "two", json_mode=True) == "second"

    assert len(llm.calls) == 2
    assert llm.calls[0].user == "one"
    assert llm.calls[1].json_mode is True
    assert llm.calls[1].temperature == 0.2


async def test_fake_llm_raises_when_script_exhausted() -> None:
    llm = FakeLLMClient([])
    with pytest.raises(RuntimeError, match="no scripted responses"):
        await llm.complete("system", "user")


def test_get_llm_fake_from_settings() -> None:
    llm = get_llm(Settings(llm_provider="fake"))
    assert isinstance(llm, FakeLLMClient)
