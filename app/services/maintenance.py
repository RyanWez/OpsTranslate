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

# Default message — clean English, shown when admin has not customised.
DEFAULT_MESSAGE: str = (
    "🔧 <b>Bot is under maintenance</b>\n\n"
    "Translation service is temporarily unavailable.\n"
    "Please try again in a few minutes."
)

DEFAULT_RESUMED_MESSAGE: str = (
    "🟢 <b>Bot is back online</b>\n\n"
    "Maintenance is complete and translations are fully restored.\n"
    "You can continue sending messages to translate normally."
)

DEFAULT_TITLE: str = "Under Maintenance"


@dataclass
class MaintenanceConfig:
    enabled: bool = False
    message: str = DEFAULT_MESSAGE
    resumed_message: str = DEFAULT_RESUMED_MESSAGE
    allow_admin_bypass: bool = False
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
            resumed_message=str(data.get("resumed_message") or DEFAULT_RESUMED_MESSAGE).strip() or DEFAULT_RESUMED_MESSAGE,
            allow_admin_bypass=bool(data.get("allow_admin_bypass", False)),
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
    from .. import config as configmod
    if user_id in configmod.ADMIN_USER_IDS:
        return True
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
    resumed_message: str | None = None,
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
        resumed_message=(resumed_message.strip() if isinstance(resumed_message, str) and resumed_message.strip() else current.resumed_message),
        title=(title.strip() if isinstance(title, str) and title.strip() else current.title),
        allow_admin_bypass=allow_admin_bypass if allow_admin_bypass is not None else current.allow_admin_bypass,
        updated_by=updated_by,
        updated_at=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    )
    # Ensure non-empty
    if not new_cfg.message.strip():
        new_cfg.message = DEFAULT_MESSAGE
    if not new_cfg.resumed_message.strip():
        new_cfg.resumed_message = DEFAULT_RESUMED_MESSAGE
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


async def broadcast_maintenance_notification(
    bot,
    *,
    enabled: bool,
    custom_message: str | None = None,
    custom_resumed_message: str | None = None,
) -> int:
    """Broadcast maintenance status change (ON / OFF) to all active staff users and ops group."""
    import asyncio
    from .. import config as configmod
    from ..bot import strings as stringsmod

    # 1. Determine recipients
    user_ids: set[int] = set()

    # Query DB for all active allowed users and registered users
    from ..store import db as dbmod
    if dbmod.is_configured():
        try:
            from sqlalchemy import select
            from ..store.models import AllowedUser, UserSettings

            async with dbmod.session() as sess:
                res = await sess.execute(select(AllowedUser.user_id).where(AllowedUser.active.is_(True)))
                for uid in res.scalars():
                    user_ids.add(int(uid))
                res = await sess.execute(select(UserSettings.user_id))
                for uid in res.scalars():
                    user_ids.add(int(uid))
        except Exception as exc:
            log.warning("broadcast_fetch_recipients_failed: %s", exc)

    # Seed lists from config
    for uid in getattr(configmod, "ADMIN_USER_IDS", []):
        user_ids.add(int(uid))
    for uid in getattr(configmod, "ALLOWED_USER_IDS", []):
        user_ids.add(int(uid))

    chat_ids: list[int] = list(user_ids)
    group_id = getattr(configmod, "GROUP_CHAT_ID", None)
    if group_id and group_id not in chat_ids:
        chat_ids.append(group_id)

    if not chat_ids or not bot:
        log.info("broadcast_maintenance_skipped: recipients=%d bot=%s", len(chat_ids), bool(bot))
        return 0

    # 2. Build message text
    if enabled:
        text = stringsmod.maintenance_broadcast_on_text(custom_message)
    else:
        if not custom_resumed_message:
            cfg = await get_config()
            custom_resumed_message = cfg.resumed_message
        text = stringsmod.maintenance_broadcast_off_text(custom_resumed_message)

    # 3. Broadcast to all recipients
    sent_count = 0
    for cid in chat_ids:
        try:
            await bot.send_message(chat_id=cid, text=text, parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.04)  # 25 msgs/sec limit for Telegram anti-flood
        except Exception as exc:
            log.debug("broadcast_maintenance_to_%s_failed: %s", cid, exc)

    log.info("broadcast_maintenance_finished: enabled=%s sent=%d/%d", enabled, sent_count, len(chat_ids))
    return sent_count
