"""Database access for dynamic AI Providers (Admin Panel is the source of truth).

Providers live ONLY in the PostgreSQL providers table, managed via the
/admin Providers page. There is intentionally NO env fallback
(PROVIDERS_JSON / PROVIDER_* were removed) and NO file fallback
(data/providers.json was removed): a missing/empty table returns zero
providers so the misconfiguration is loud (healthz 503, startup error log)
instead of silently running on stale credentials.
"""
from __future__ import annotations

import logging

from .. import config
from ..services.provider import Provider as ServiceProvider, ProviderRouter
from . import db as dbmod
from .models import Provider as DBProvider

log = logging.getLogger("opstranslate.store.providers")


async def get_active_service_providers() -> list[ServiceProvider]:
    """Load providers for ProviderRouter from PostgreSQL.

    Returns [] when the DB is unconfigured, unreachable, or the table holds
    no enabled rows - callers treat that as a hard misconfiguration.
    """
    if not dbmod.is_configured():
        log.error("DATABASE_URL is not configured - no providers available (add via /admin)")
        return []
    try:
        import asyncio
        from sqlalchemy import select

        async def _fetch():
            async with dbmod.session() as sess:
                result = await sess.execute(
                    select(DBProvider)
                    .where(DBProvider.enabled.is_(True))
                    .order_by(DBProvider.priority.asc(), DBProvider.id.asc())
                )
                return result.scalars().all()

        db_rows = await asyncio.wait_for(_fetch(), timeout=10.0)
        if not db_rows:
            log.error("providers table has no enabled rows - add providers via /admin")
            return []
        providers = []
        for row in db_rows:
            providers.append(
                ServiceProvider(
                    name=row.name,
                    base_url=row.base_url.rstrip("/"),
                    api_key=row.api_key,
                    model=row.model,
                    priority=row.priority,
                    enabled=row.enabled,
                    timeout_s=float(row.timeout_ms / 1000.0) if row.timeout_ms else config.PROVIDER_TIMEOUT_S,
                )
            )
        return providers
    except Exception as exc:
        log.error("failed to load providers from db (no fallback - fix DB): %s", exc)
        return []


async def sync_router_providers(router: ProviderRouter) -> list[ServiceProvider]:
    """Fetch active providers and reload ProviderRouter in memory."""
    active = await get_active_service_providers()
    router.reload_providers(active)
    log.info("synced %d active providers to router", len(active))
    return active
