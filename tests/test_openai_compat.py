import json

import httpx
import pytest

from agent.config import Settings
from agent.llm import OpenAICompatClient, OpenAICompatError, get_llm


def make_client(handler) -> OpenAICompatClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return OpenAICompatClient(
        base_url="https://api.example.com/v1",
        api_key="free-tier-key",
        model="llama-3.1-8b-instant",
        client=http_client,
    )


async def test_openai_compat_request_shape_and_response() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client = make_client(handler)
    result = await client.complete("system", "user", json_mode=True, temperature=0.4)
    assert result == "ok"

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.4
    assert seen["url"] == "https://api.example.com/v1/chat/completions"
    assert seen["authorization"] == "Bearer free-tier-key"


async def test_openai_compat_unreachable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    client = make_client(handler)
    with pytest.raises(OpenAICompatError, match="Cannot reach LLM endpoint"):
        await client.complete("system", "user")


def test_get_llm_openai_compat_from_settings() -> None:
    settings = Settings(
        llm_provider="openai_compat",
        llm_base_url="https://api.example.com/v1",
        llm_model="free-model",
        llm_api_key="key",
    )
    client = get_llm(settings)
    assert isinstance(client, OpenAICompatClient)
