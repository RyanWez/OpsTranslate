"""Database access and sync helpers for dynamic AI Providers."""
from __future__ import annotations

import logging
from typing import Optional

from .. import config
from ..services.provider import Provider as ServiceProvider, ProviderRouter
from . import db as dbmod
from .models import Provider as DBProvider

log = logging.getLogger("opstranslate.store.providers")


async def get_active_service_providers() -> list[ServiceProvider]:
    """Load active providers for ProviderRouter.
    
    Reads from PostgreSQL if configured and populated; falls back gracefully
    to config.provider_defs() from environment variables.
    """
    if dbmod.is_configured():
        try:
            import asyncio
            from sqlalchemy import select

            async def _fetch():
                async with dbmod.session() as sess:
                    result = await sess.execute(
                        select(DBProvider)
                        .where(DBProvider.enabled == True)  # noqa: E712
                        .order_by(DBProvider.priority.asc(), DBProvider.id.asc())
                    )
                    return result.scalars().all()

            db_rows = await asyncio.wait_for(_fetch(), timeout=2.0)
            if db_rows:
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
            log.warning("failed to load providers from db, falling back to env: %s", exc)

    # Fallback to env-configured providers
    providers = []
    for d in config.provider_defs():
        providers.append(
            ServiceProvider(
                name=d.get("name", "primary"),
                base_url=(d.get("base_url") or "").rstrip("/"),
                api_key=d.get("api_key") or "",
                model=d.get("model") or "",
                priority=int(d.get("priority", 1)),
                enabled=bool(d.get("enabled", True)),
                timeout_s=float(d.get("timeout_s", config.PROVIDER_TIMEOUT_S)),
            )
        )
    return providers


async def sync_router_providers(router: ProviderRouter) -> list[ServiceProvider]:
    """Fetch active providers and reload ProviderRouter in memory."""
    active = await get_active_service_providers()
    router.reload_providers(active)
    log.info("synced %d active providers to router", len(active))
    return active
