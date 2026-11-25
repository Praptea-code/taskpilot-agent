"""add agent sessions

Revision ID: 9a1b2c3d4e5f
Revises: 3b0d1e3883bb
Create Date: 2026-11-25 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "3b0d1e3883bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_action_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["scheduled_action_id"], ["scheduled_actions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_sessions_goal_id"), "agent_sessions", ["goal_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_sessions_scheduled_action_id"),
        "agent_sessions",
        ["scheduled_action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_sessions_user_id"), "agent_sessions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_sessions_user_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_scheduled_action_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_goal_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
