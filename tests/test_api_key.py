from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.db.session import get_session
from agent.main import create_app
from agent.models import Base


@pytest.fixture
async def api_client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await engine.dispose()


async def register_user(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post(
        "/users",
        json={"name": "User", "email": email, "timezone": "UTC"},
    )
    assert response.status_code == 201
    return response.json()["api_key"]


async def test_missing_api_key_returns_401(api_client) -> None:
    response = await api_client.get("/goals")

    assert response.status_code == 401


async def test_invalid_api_key_returns_401(api_client) -> None:
    response = await api_client.get(
        "/goals", headers={"Authorization": "Bearer invalid"}
    )

    assert response.status_code == 401


async def test_cross_tenant_goal_access_returns_404(api_client) -> None:
    key_a = await register_user(api_client, "a@example.com")
    key_b = await register_user(api_client, "b@example.com")
    created = await api_client.post(
        "/goals",
        headers={"Authorization": f"Bearer {key_a}"},
        json={"raw_input_text": "Private goal", "domain": "general", "auto_plan": False},
    )
    goal_id = created.json()["id"]

    read = await api_client.get(
        f"/goals/{goal_id}", headers={"Authorization": f"Bearer {key_b}"}
    )

    assert read.status_code == 404
