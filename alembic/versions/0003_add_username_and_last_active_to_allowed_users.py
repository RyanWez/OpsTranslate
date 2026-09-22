"""add username and last_active_at columns to allowed_users

Revision ID: 0003_add_user_profile
Revises: 0002_add_provider_to_usage_log
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_user_profile"
down_revision = "0002_add_provider_to_usage_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("allowed_users", sa.Column("username", sa.String(64), nullable=True))
    op.create_index("ix_allowed_users_username", "allowed_users", ["username"])
    op.add_column(
        "allowed_users",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("allowed_users", "last_active_at")
    op.drop_index("ix_allowed_users_username", table_name="allowed_users")
    op.drop_column("allowed_users", "username")
