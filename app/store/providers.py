"""Database access and persistent local storage helpers for dynamic AI Providers."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .. import config
from ..services.provider import Provider as ServiceProvider, ProviderRouter
from . import db as dbmod
from .models import Provider as DBProvider

log = logging.getLogger("opstranslate.store.providers")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PROVIDERS_FILE = DATA_DIR / "providers.json"


def load_stored_providers() -> list[dict]:
    """Load providers from data/providers.json or initialize from env."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PROVIDERS_FILE.exists():
        try:
            with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception as exc:
            log.warning("failed to load providers.json: %s", exc)

    # Initial seed from config.provider_defs() or default working providers
    seed = []
    defs = config.provider_defs()
    has_gemini = any(d.get("name") == "gemini" for d in defs)

    if not has_gemini and len(defs) == 1 and defs[0].get("name") == "primary":
        seed = [
            {
                "id": 1,
                "name": "gemini",
                "base_url": "https://gemini-api.online/v1",
                "api_key": "sk-qOu89KfOdTSGfmhy4bfvAtyjAnunDznFCGwyFAugA1QGQ0W6",
                "model": "gemini-3.8-flash-tiered",
                "priority": 1,
                "enabled": True,
                "timeout_s": 30.0,
            },
            {
                "id": 2,
                "name": "vsllm-primary",
                "base_url": "https://vsllm.cc/v1",
                "api_key": "sk-RcahJnr8Sut3NXPGTCAIPwwjq5WFpHkoDNLsxzKR1SVBWk6y",
                "model": "gemini-3.5-flash-lite",
                "priority": 2,
                "enabled": True,
                "timeout_s": 30.0,
            },
            {
                "id": 3,
                "name": "Careke",
                "base_url": defs[0].get("base_url") or "https://api.careke.cn/v1",
                "api_key": defs[0].get("api_key") or "",
                "model": defs[0].get("model") or "gemini-3-flash",
                "priority": 3,
                "enabled": False,  # Off by default as user location is blocked
                "timeout_s": 30.0,
            },
        ]
    else:
        for idx, d in enumerate(defs):
            name = d.get("name", f"provider-{idx+1}")
            if name == "primary":
                name = "Careke" if "careke" in (d.get("base_url") or "") else "primary"
            seed.append({
                "id": idx + 1,
                "name": name,
                "base_url": (d.get("base_url") or "").rstrip("/"),
                "api_key": d.get("api_key") or "",
                "model": d.get("model") or "",
                "priority": int(d.get("priority", idx + 1)),
                "enabled": bool(d.get("enabled", True)),
                "timeout_s": float(d.get("timeout_s", config.PROVIDER_TIMEOUT_S)),
            })

    save_stored_providers(seed)
    return seed


def save_stored_providers(providers: list[dict]) -> None:
    """Save provider list atomically to data/providers.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = DATA_DIR / "providers.json.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(providers, f, indent=2, ensure_ascii=False)
    temp_file.replace(PROVIDERS_FILE)


async def get_active_service_providers() -> list[ServiceProvider]:
    """Load active providers for ProviderRouter.
    
    Reads from PostgreSQL if configured and populated; falls back gracefully
    to persistent data/providers.json.
    """
    if dbmod.is_configured():
        try:
            import asyncio
            from sqlalchemy import select

            async def _fetch():
                async with dbmod.session() as sess:
                    result = await sess.execute(
                        select(DBProvider)
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
            log.warning("failed to load providers from db, falling back to local file: %s", exc)

    # Fallback to persistent data/providers.json
    stored = load_stored_providers()
    providers = []
    for d in stored:
        providers.append(
            ServiceProvider(
                name=d["name"],
                base_url=d["base_url"].rstrip("/"),
                api_key=d.get("api_key") or "",
                model=d["model"],
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

