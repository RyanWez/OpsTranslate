"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allowed_users",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("display_name", sa.Text()),
        sa.Column("role", sa.String(16), server_default="staff"),
        sa.Column("daily_soft_cap", sa.Integer(), server_default="200"),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column("added_by", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("target_lang", sa.String(8), server_default="en"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), unique=True, nullable=False),
        sa.Column("kind", sa.String(32), server_default="openai_compatible"),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_enc", postgresql.BYTEA()),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="1"),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column("timeout_ms", sa.Integer(), server_default="8000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "provider_health",
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), primary_key=True),
        sa.Column("state", sa.String(16), server_default="closed"),
        sa.Column("fail_count", sa.Integer(), server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version", sa.Integer(), unique=True, nullable=False),
        sa.Column("status", sa.String(16), server_default="draft"),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "term_concepts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_version", sa.Integer(), index=True, nullable=False),
        sa.Column("concept_key", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column("approved", sa.Boolean(), server_default="false"),
        sa.Column("notes", sa.Text()),
    )
    op.create_table(
        "term_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("term_concepts.id"), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("is_source", sa.Boolean(), server_default="true"),
        sa.Column("priority", sa.Integer(), server_default="0"),
    )
    op.create_table(
        "term_outputs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("term_concepts.id"), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.BigInteger()),
    )
    op.create_table(
        "deny_terms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_version", sa.Integer(), index=True, nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
    )
    op.create_table(
        "policy_tests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_version", sa.Integer(), index=True, nullable=False),
        sa.Column("src_lang", sa.String(8), nullable=False),
        sa.Column("dst_lang", sa.String(8), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("expected_contains", sa.Text()),
        sa.Column("must_not_contain", sa.Text()),
    )
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), index=True, nullable=False),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "usage_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("user_id", sa.BigInteger(), index=True),
        sa.Column("src_lang", sa.String(8)),
        sa.Column("dst_lang", sa.String(8)),
        sa.Column("text_hash", sa.String(16)),
        sa.Column("char_len", sa.Integer()),
        sa.Column("provider_id", sa.Integer()),
        sa.Column("cache_hit", sa.Boolean()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("policy_version", sa.Integer()),
        sa.Column("policy_hits", postgresql.JSONB()),
        sa.Column("deny_hits", sa.Integer()),
        sa.Column("ratio", sa.Numeric(4, 2)),
        sa.Column("status", sa.String(32), index=True),
        sa.Column("error_code", sa.String(64)),
    )
    op.create_index("ix_usage_log_user_ts", "usage_log", ["user_id", sa.text("ts DESC")])
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.BigInteger()),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.Text()),
        sa.Column("before", postgresql.JSONB()),
        sa.Column("after", postgresql.JSONB()),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "alert_state",
        sa.Column("fingerprint", sa.String(128), primary_key=True),
        sa.Column("level", sa.String(8)),
        sa.Column("first_seen", sa.DateTime(timezone=True)),
        sa.Column("last_sent", sa.DateTime(timezone=True)),
        sa.Column("count", sa.Integer(), server_default="0"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "settings", "alert_state", "admin_audit", "usage_log", "prompts",
        "policy_tests", "deny_terms", "term_outputs", "term_variants",
        "term_concepts", "policy_versions", "provider_health", "providers",
        "user_settings", "allowed_users",
    ):
        op.drop_table(table)
