"""add inbox messages

Revision ID: 6e3a4b5c6d7f
Revises: 5d2e3f4a6b7c
Create Date: 2026-11-25 13:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e3a4b5c6d7f"
down_revision: str | None = "5d2e3f4a6b7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inbox_messages_lead_id"), "inbox_messages", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_inbox_messages_received_at"), "inbox_messages", ["received_at"], unique=False
    )
    op.create_index(
        op.f("ix_inbox_messages_user_id"), "inbox_messages", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inbox_messages_user_id"), table_name="inbox_messages")
    op.drop_index(op.f("ix_inbox_messages_received_at"), table_name="inbox_messages")
    op.drop_index(op.f("ix_inbox_messages_lead_id"), table_name="inbox_messages")
    op.drop_table("inbox_messages")
