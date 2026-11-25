from sqlalchemy import text

from agent.db.session import get_sessionmaker


async def test_session_runs_select_one() -> None:
    maker = get_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with maker() as session:
        result = await session.execute(text("SELECT 1"))

    assert result.scalar_one() == 1
