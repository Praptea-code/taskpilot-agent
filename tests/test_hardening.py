from collections.abc import AsyncIterator

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent import main as main_module
from agent.api import credentials as credentials_module
from agent.config import Settings
from agent.core.credentials import decrypt_credential
from agent.db.session import get_session
from agent.models import Base, UserCredential


@pytest.fixture
async def hardened_client(
    tmp_path, monkeypatch
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker, Settings]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'hardening.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(rate_limit_per_minute=0, credentials_key=key)

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(credentials_module, "get_settings", lambda: settings)
    app = main_module.create_app()
    app.dependency_overrides[get_session] = override_get_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, maker, settings
    await engine.dispose()


async def test_rate_limit_returns_429(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: Settings(rate_limit_per_minute=1),
    )
    app = main_module.create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get("/health")
        second = await client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 429


async def test_credentials_round_trip_and_never_returned(hardened_client) -> None:
    client, maker, settings = hardened_client
    registration = await client.post(
        "/users", json={"name": "User", "email": "cred@example.com"}
    )
    api_key = registration.json()["api_key"]
    headers = {"Authorization": f"Bearer {api_key}"}

    saved = await client.post(
        "/users/me/credentials",
        headers=headers,
        json={"service": "google_calendar", "value": "secret-token"},
    )

    assert saved.status_code == 201
    assert "secret-token" not in saved.text
    assert saved.json()["service"] == "google_calendar"

    listed = await client.get("/users/me/credentials", headers=headers)

    assert listed.status_code == 200
    assert "secret-token" not in listed.text
    assert "encrypted_value" not in listed.json()[0]

    assert settings.credentials_key
    async with maker() as session:
        row = await session.scalar(select(UserCredential))
        assert row is not None
        assert row.encrypted_value != "secret-token"


async def test_credential_can_be_decrypted_with_configured_key(hardened_client) -> None:
    client, maker, settings = hardened_client
    registration = await client.post(
        "/users", json={"name": "User", "email": "decrypt@example.com"}
    )
    api_key = registration.json()["api_key"]
    await client.post(
        "/users/me/credentials",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"service": "google_calendar", "value": "secret-token"},
    )

    async with maker() as session:
        row = await session.scalar(select(UserCredential))
        assert row is not None
        assert decrypt_credential(row.encrypted_value, settings.credentials_key) == "secret-token"
