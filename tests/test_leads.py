import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.models import Base, Lead, User
from agent.schemas.sales import SendEmailPayload


async def test_lead_crud(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'leads.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with maker() as session:
        user = User(name="User", email="user@example.com")
        session.add(user)
        await session.flush()
        lead = Lead(
            user_id=user.id,
            name="Alice",
            email="alice@example.com",
            company="Acme",
            stage="new",
            notes="First touch",
        )
        session.add(lead)
        await session.commit()
        lead_id = lead.id

    async with maker() as session:
        lead = await session.get(Lead, lead_id)
        assert lead is not None
        assert lead.stage == "new"
        lead.stage = "contacted"
        lead.last_contacted_at = now
        await session.commit()

    async with maker() as session:
        result = await session.execute(select(Lead).where(Lead.user_id == 1))
        lead = result.scalar_one()
        assert lead.stage == "contacted"
        assert lead.last_contacted_at is not None
        assert lead.last_contacted_at.replace(tzinfo=UTC) == now
        await session.delete(lead)
        await session.commit()

    async with maker() as session:
        result = await session.execute(select(Lead))
        assert list(result.scalars().all()) == []
    await engine.dispose()


def test_send_email_payload_validation() -> None:
    payload = SendEmailPayload.model_validate(
        {"lead_id": 4, "template": "intro", "step": 2}
    )

    assert payload.lead_id == 4
    assert payload.template == "intro"
    assert payload.step == 2
    with pytest.raises(ValidationError):
        SendEmailPayload.model_validate({"lead_id": 4, "template": "intro", "step": 0})


def test_migration_creates_and_drops_leads(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert "leads" in inspect(connection).get_table_names()
    engine.dispose()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert "leads" not in inspect(connection).get_table_names()
    engine.dispose()
