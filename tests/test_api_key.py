import httpx

from agent import main as main_module
from agent.config import Settings


def build_client(monkeypatch, api_key: str) -> httpx.AsyncClient:
    monkeypatch.setattr(main_module, "get_settings", lambda: Settings(api_key=api_key))
    app = main_module.create_app()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_guard_rejects_missing_key(monkeypatch) -> None:
    async with build_client(monkeypatch, "secret") as client:
        response = await client.get("/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


async def test_guard_rejects_wrong_key(monkeypatch) -> None:
    async with build_client(monkeypatch, "secret") as client:
        response = await client.get("/health", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401


async def test_guard_allows_correct_key(monkeypatch) -> None:
    async with build_client(monkeypatch, "secret") as client:
        response = await client.get("/health", headers={"X-API-Key": "secret"})

    assert response.status_code == 200


async def test_guard_disabled_without_api_key(monkeypatch) -> None:
    async with build_client(monkeypatch, "") as client:
        response = await client.get("/health")

    assert response.status_code == 200
