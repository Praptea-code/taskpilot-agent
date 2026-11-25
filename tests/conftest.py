from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.db.session import get_session
from agent.main import create_app
from agent.models import Base, User


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        async with maker() as session:
            session.add_all(
                [
                    User(name="User A", email="a@example.com"),
                    User(name="User B", email="b@example.com"),
                ]
            )
            await session.commit()
        yield test_client, maker

    await engine.dispose()
