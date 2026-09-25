"""Maintenance Mode service — DB-backed global kill-switch.

Stored in the generic ``settings`` table under key ``maintenance_mode`` so no
migration is required.  A short-lived in-memory cache (TTL 10 s) keeps the
hot path (every Telegram message) from hitting Postgres on every request.

Schema in ``settings.value``:
    {
        "enabled": bool,
        "message": str,               # custom HTML message shown to users
        "allow_admin_bypass": bool,   # admins still get translations
        "title": str,                 # short banner title
        "updated_at": str | None,
        "updated_by": int | None,
    }

When DB is unavailable the service fail-opens (maintenance OFF) so a DB
outage never makes the bot look like it is in maintenance.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any

log = logging.getLogger("opstranslate.maintenance")

SETTING_KEY = "maintenance_mode"

# Default message — Burmese + English, shown when admin has not customised.
DEFAULT_MESSAGE: str = (
    "🔧 <b>Bot ကို Update လုပ်နေပါတယ်</b>\n\n"
    "လောလောဆယ် ဘာသာပြန်ဝန်ဆောင်မှု ခေတ္တ ရပ်ဆိုင်းထားပါတယ်။\n"
    "မကြာခင် ပြန်လည်အသုံးပြုနိုင်ပါမယ် — ခဏစောင့်ပေးပါ။\n\n"
    "🔧 <b>Bot is under maintenance</b>\n\n"
    "Translation service is temporarily unavailable.\n"
    "Please try again in a few minutes."
)

DEFAULT_TITLE: str = "Under Maintenance"


@dataclass
class MaintenanceConfig:
    enabled: bool = False
    message: str = DEFAULT_MESSAGE
    allow_admin_bypass: bool = True
    title: str = DEFAULT_TITLE
    updated_at: str | None = None
    updated_by: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MaintenanceConfig":
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            message=str(data.get("message") or DEFAULT_MESSAGE).strip() or DEFAULT_MESSAGE,
            allow_admin_bypass=bool(data.get("allow_admin_bypass", True)),
            title=str(data.get("title") or DEFAULT_TITLE).strip() or DEFAULT_TITLE,
            updated_at=data.get("updated_at"),
            updated_by=data.get("updated_by"),
        )


# ---------------------------------------------------------------------------
# In-memory cache — keeps the hot path off Postgres
# ---------------------------------------------------------------------------
_CACHE_TTL_S = 10.0
_cached: MaintenanceConfig | None = None
_cached_at: float = 0.0


def _is_cache_valid() -> bool:
    return _cached is not None and (time.monotonic() - _cached_at) < _CACHE_TTL_S


def invalidate_cache() -> None:
    global _cached, _cached_at
    _cached = None
    _cached_at = 0.0


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def _load_from_db() -> MaintenanceConfig:
    from ..store import db as dbmod

    if not dbmod.is_configured():
        return MaintenanceConfig()

    try:
        from sqlalchemy import select
        from ..store.models import Setting

        async with dbmod.session() as sess:
            res = await sess.execute(select(Setting).where(Setting.key == SETTING_KEY))
            setting = res.scalar_one_or_none()
            if setting and setting.value and isinstance(setting.value, dict):
                return MaintenanceConfig.from_dict(setting.value)
    except Exception as exc:
        log.warning("maintenance_load_failed: %s", exc)

    return MaintenanceConfig()


async def _save_to_db(cfg: MaintenanceConfig) -> None:
    from ..store import db as dbmod
    from sqlalchemy import select
    from ..store.models import Setting

    if not dbmod.is_configured():
        log.info("maintenance_save_skipped_no_db: enabled=%s", cfg.enabled)
        return

    try:
        async with dbmod.session() as sess:
            res = await sess.execute(select(Setting).where(Setting.key == SETTING_KEY))
            setting = res.scalar_one_or_none()
            if setting is None:
                setting = Setting(key=SETTING_KEY, value=cfg.to_dict())
                sess.add(setting)
            else:
                setting.value = cfg.to_dict()
            await sess.commit()
    except Exception as exc:
        log.error("maintenance_save_failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def get_config(*, force_refresh: bool = False) -> MaintenanceConfig:
    """Return the current maintenance config (cached, TTL 10 s)."""
    global _cached, _cached_at
    if not force_refresh and _is_cache_valid():
        return _cached  # type: ignore[return-value]
    cfg = await _load_from_db()
    _cached = cfg
    _cached_at = time.monotonic()
    return cfg


async def is_enabled() -> bool:
    """Hot-path helper — is maintenance ON right now?"""
    cfg = await get_config()
    return cfg.enabled


async def get_message() -> str:
    cfg = await get_config()
    return cfg.message or DEFAULT_MESSAGE


async def get_title() -> str:
    cfg = await get_config()
    return cfg.title or DEFAULT_TITLE


async def should_bypass(user_id: int, user_store=None) -> bool:
    """Return True if this user should bypass maintenance (admin)."""
    cfg = await get_config()
    if not cfg.enabled:
        return False
    if not cfg.allow_admin_bypass:
        return False
    if user_store is None:
        return False
    try:
        allowed, role = await user_store.is_allowed(user_id)
        return role == "admin"
    except Exception:
        return False


async def set_config(
    *,
    enabled: bool,
    message: str | None = None,
    title: str | None = None,
    allow_admin_bypass: bool | None = None,
    updated_by: int | None = None,
) -> MaintenanceConfig:
    """Persist a new maintenance config and invalidate the cache."""
    # Load current to merge partial updates
    current = await _load_from_db()

    new_cfg = MaintenanceConfig(
        enabled=enabled,
        message=(message.strip() if isinstance(message, str) and message.strip() else current.message),
        title=(title.strip() if isinstance(title, str) and title.strip() else current.title),
        allow_admin_bypass=allow_admin_bypass if allow_admin_bypass is not None else current.allow_admin_bypass,
        updated_by=updated_by,
        updated_at=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    )
    # Ensure non-empty
    if not new_cfg.message.strip():
        new_cfg.message = DEFAULT_MESSAGE
    if not new_cfg.title.strip():
        new_cfg.title = DEFAULT_TITLE

    await _save_to_db(new_cfg)

    # Update in-memory cache immediately
    global _cached, _cached_at
    _cached = new_cfg
    _cached_at = time.monotonic()

    # Broadcast SSE so every open Admin Panel updates live
    try:
        from ..admin.sse import broadcaster
        broadcaster.broadcast("maintenance_changed", new_cfg.to_dict())
        broadcaster.broadcast("overview_changed", {})
    except Exception:
        pass

    log.info("maintenance_config_updated: enabled=%s by=%s", enabled, updated_by)
    return new_cfg
