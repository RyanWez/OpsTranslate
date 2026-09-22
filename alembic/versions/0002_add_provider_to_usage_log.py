"""add provider column to usage_log

Revision ID: 0002_add_provider_to_usage_log
Revises: 0001_initial
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_provider_to_usage_log"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_log", sa.Column("provider", sa.String(64), nullable=True))
    op.create_index("ix_usage_log_provider", "usage_log", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_usage_log_provider", table_name="usage_log")
    op.drop_column("usage_log", "provider")
