import json

import httpx
import pytest

from agent.config import Settings
from agent.llm import OllamaClient, OllamaError, get_llm


def make_client(handler) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return OllamaClient(client=http_client)


async def test_ollama_request_shape_and_response() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"message": {"content": "hello from ollama"}})

    client = make_client(handler)
    result = await client.complete("system prompt", "user prompt", json_mode=True)
    assert result == "hello from ollama"

    captured = seen["payload"]
    assert isinstance(captured, dict)
    assert captured["format"] == "json"
    assert captured["model"] == "qwen2.5:7b-instruct"
    assert seen["url"] == "http://localhost:11434/api/chat"


async def test_ollama_unreachable_has_friendly_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    client = make_client(handler)
    with pytest.raises(OllamaError, match="ollama serve"):
        await client.complete("system", "user")


def test_get_llm_ollama_from_settings() -> None:
    client = get_llm(Settings(llm_provider="ollama", ollama_host="http://example.invalid"))
    assert isinstance(client, OllamaClient)
