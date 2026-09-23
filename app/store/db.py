"""Database engine/session helpers. Optional: the bot runs without a database.

When DATABASE_URL is unset, all persistence degrades gracefully:
user settings fall back to an in-memory dict, the allowlist falls back to
the TEST_ALLOW_ALL flag / env seed, and usage logging is skipped.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

log = logging.getLogger("opstranslate.db")

_engine = None
_session_factory = None


def is_configured() -> bool:
    from .. import config

    return bool(config.DATABASE_URL)


def get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        from .. import config

        import urllib.parse

        url = config.DATABASE_URL
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]

        parsed = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        connect_args = {}
        if "sslmode" in query_params or "ssl" in query_params or (parsed.hostname and "supabase" in parsed.hostname):
            connect_args["ssl"] = "require"
        query_params.pop("sslmode", None)
        query_params.pop("channel_binding", None)
        query_params.pop("pgbouncer", None)
        new_query = urllib.parse.urlencode({k: v[0] for k, v in query_params.items()})
        cleaned_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

        if cleaned_url.startswith("postgresql"):
            from sqlalchemy.pool import AsyncAdaptedQueuePool

            connect_args["timeout"] = 25.0
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0
            connect_args["prepared_statement_name_func"] = lambda: False
            _engine = create_async_engine(
                cleaned_url,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=5,
                max_overflow=10,
                pool_timeout=10.0,
                pool_recycle=300,
                pool_pre_ping=False,
                connect_args=connect_args,
            )
        else:
            from sqlalchemy.pool import NullPool

            _engine = create_async_engine(
                cleaned_url,
                poolclass=NullPool,
                connect_args=connect_args,
            )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def session() -> AsyncIterator:
    factory = get_session_factory()
    async with factory() as sess:
        yield sess


async def ping() -> bool:
    if not is_configured():
        return True  # nothing to check
    try:
        from sqlalchemy import text

        async with session() as sess:
            await sess.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("db_ping_failed", extra={"error": str(exc)})
        return False


async def close() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
