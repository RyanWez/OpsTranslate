"""SQLAlchemy models for the Neon Postgres schema (spec section 10).

Privacy by construction: there is NO column anywhere for message text.
usage_log stores text_hash and char_len only - never content.
"""
from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


# Use JSONB on Postgres, plain JSON elsewhere (tests use SQLite).
JSONType = JSONB().with_variant(JSON(), "sqlite")


class AllowedUser(Base):
    __tablename__ = "allowed_users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="staff")  # admin | staff
    daily_soft_cap: Mapped[int] = mapped_column(Integer, default=200)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    last_active_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_lang: Mapped[str] = mapped_column(String(8), default="en")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32), default="openai_compatible")
    base_url: Mapped[str] = mapped_column(Text)
    api_key_enc: Mapped[bytes | None] = mapped_column(BYTEA)
    model: Mapped[str] = mapped_column(String(128))
    priority: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=8000)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    @property
    def api_key(self) -> str:
        from .crypto import decrypt_secret
        return decrypt_secret(self.api_key_enc)

    @api_key.setter
    def api_key(self, val: str) -> None:
        from .crypto import encrypt_secret
        self.api_key_enc = encrypt_secret(val)


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(16), default="closed")  # closed|open|half_open
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    opened_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|published|retired
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class TermConcept(Base):
    __tablename__ = "term_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_version: Mapped[int] = mapped_column(Integer, index=True)
    concept_key: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class TermVariant(Base):
    __tablename__ = "term_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept_id: Mapped[int] = mapped_column(Integer, ForeignKey("term_concepts.id"))
    lang: Mapped[str] = mapped_column(String(8))  # my|en|zh
    pattern: Mapped[str] = mapped_column(Text)
    is_source: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # longest-match ordering


class TermOutput(Base):
    __tablename__ = "term_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept_id: Mapped[int] = mapped_column(Integer, ForeignKey("term_concepts.id"))
    lang: Mapped[str] = mapped_column(String(8))
    output_text: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int | None] = mapped_column(BigInteger)


class DenyTerm(Base):
    __tablename__ = "deny_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_version: Mapped[int] = mapped_column(Integer, index=True)
    lang: Mapped[str] = mapped_column(String(8))
    term: Mapped[str] = mapped_column(Text)


class PolicyTest(Base):
    __tablename__ = "policy_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_version: Mapped[int] = mapped_column(Integer, index=True)
    src_lang: Mapped[str] = mapped_column(String(8))
    dst_lang: Mapped[str] = mapped_column(String(8))
    input_text: Mapped[str] = mapped_column(Text)
    expected_contains: Mapped[str | None] = mapped_column(Text)
    must_not_contain: Mapped[str | None] = mapped_column(Text)


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class UsageLog(Base):
    """Metadata only - NEVER message text."""

    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    src_lang: Mapped[str | None] = mapped_column(String(8))
    dst_lang: Mapped[str | None] = mapped_column(String(8))
    text_hash: Mapped[str | None] = mapped_column(String(16))
    char_len: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_id: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    policy_version: Mapped[int | None] = mapped_column(Integer)
    policy_hits: Mapped[list | None] = mapped_column(JSONType)
    deny_hits: Mapped[int | None] = mapped_column(Integer)
    ratio: Mapped[float | None] = mapped_column(Numeric(4, 2))
    status: Mapped[str | None] = mapped_column(String(32), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))


Index("ix_usage_log_user_ts", UsageLog.user_id, UsageLog.ts.desc())


class AdminAudit(Base):
    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONType)
    after: Mapped[dict | None] = mapped_column(JSONType)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertState(Base):
    __tablename__ = "alert_state"

    fingerprint: Mapped[str] = mapped_column(String(128), primary_key=True)
    level: Mapped[str | None] = mapped_column(String(8))
    first_seen: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONType)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
