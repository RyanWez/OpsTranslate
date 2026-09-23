"""add translation_history table for staff translation audits

Revision ID: 0004_add_translation_history
Revises: 0003_add_user_profile
Create Date: 2026-09-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_add_translation_history"
down_revision = "0003_add_user_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JSON type with variant for sqlite vs postgresql
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "translation_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("src_lang", sa.String(8), nullable=False, server_default="auto"),
        sa.Column("dst_lang", sa.String(8), nullable=False, server_default="en"),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("masked_text", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("char_len", sa.Integer(), nullable=True),
        sa.Column("policy_hits", json_type, nullable=True),
        sa.Column("status", sa.String(32), nullable=True, server_default="200 OK"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_translation_history_ts", "translation_history", ["ts"])
    op.create_index("ix_translation_history_user_id", "translation_history", ["user_id"])
    op.create_index("ix_translation_history_username", "translation_history", ["username"])
    op.create_index("ix_translation_history_provider", "translation_history", ["provider"])
    op.create_index("ix_translation_history_user_ts", "translation_history", ["user_id", sa.text("ts DESC")])
    op.create_index("ix_translation_history_ts_desc", "translation_history", [sa.text("ts DESC")])


def downgrade() -> None:
    op.drop_index("ix_translation_history_ts_desc", table_name="translation_history")
    op.drop_index("ix_translation_history_user_ts", table_name="translation_history")
    op.drop_index("ix_translation_history_provider", table_name="translation_history")
    op.drop_index("ix_translation_history_username", table_name="translation_history")
    op.drop_index("ix_translation_history_user_id", table_name="translation_history")
    op.drop_index("ix_translation_history_ts", table_name="translation_history")
    op.drop_table("translation_history")
