"""add api key salt

Revision ID: 7b2c3d4e5f6a
Revises: 6e3a4b5c6d7f
Create Date: 2026-11-25 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b2c3d4e5f6a"
down_revision: str | None = "6e3a4b5c6d7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("api_key_salt", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "api_key_salt")
