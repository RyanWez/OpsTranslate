"""Alembic environment: autogenerate from app.store.models metadata.

The migration runs against DATABASE_URL at migrate time. Offline
autogenerate (alembic revision --autogenerate) needs no live database.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.store.models import Base  # noqa: E402

target_metadata = Base.metadata


def _db_url() -> str:
    import urllib.parse
    from app import config

    url = config.DATABASE_URL or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url:
        parsed = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        query_params.pop("pgbouncer", None)
        new_query = urllib.parse.urlencode({k: v[0] for k, v in query_params.items()})
        url = urllib.parse.urlunparse(parsed._replace(query=new_query))
    # Fallback lets `alembic revision --autogenerate` run without a DB.
    return url or "postgresql+psycopg://localhost/opstranslate"


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(), target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _db_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
