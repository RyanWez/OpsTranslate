"""Telegram Animated / Custom Emoji configuration and lookup service.

Provides dynamic custom animated emoji management configured via the Admin Panel,
with zero-downtime standard Unicode fallbacks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any

log = logging.getLogger("opstranslate.bot.emojis")


@dataclass
class EmojiSlot:
    key: str
    label: str
    category: str  # Pipeline | Commands | Alerts
    fallback: str
    custom_emoji_id: str = ""
    description: str = ""


DEFAULT_SLOTS: dict[str, EmojiSlot] = {
    # Translation Pipeline
    "loading": EmojiSlot(
        key="loading",
        label="Translating Indicator",
        category="Pipeline",
        fallback="⏳",
        description="Displayed in the placeholder while the provider translates",
    ),
    "header_globe": EmojiSlot(
        key="header_globe",
        label="Header Globe Icon",
        category="Pipeline",
        fallback="🌐",
        description="Displayed at the beginning of the translation output header",
    ),
    "arrow": EmojiSlot(
        key="arrow",
        label="Direction Arrow",
        category="Pipeline",
        fallback="➡️",
        description="Directional arrow between languages (e.g. MY ➡️ EN)",
    ),
    "copy_button": EmojiSlot(
        key="copy_button",
        label="Copy Button Icon",
        category="Pipeline",
        fallback="📋",
        description="Icon displayed on the 1-click Copy button (Telegram Custom Emoji ID or Unicode)",
    ),

    # Bot Commands
    "start_welcome": EmojiSlot(
        key="start_welcome",
        label="/start Welcome Wave",
        category="Commands",
        fallback="👋",
        description="Greeting wave icon in /start welcome message",
    ),
    "auto_mode": EmojiSlot(
        key="auto_mode",
        label="Auto Mode Exchange",
        category="Commands",
        fallback="🔄",
        description="Automatic language toggle description in /start and /tr",
    ),
    "help_book": EmojiSlot(
        key="help_book",
        label="/help Guide Book",
        category="Commands",
        fallback="📖",
        description="Header icon in /help usage instructions",
    ),
    "help_privacy": EmojiSlot(
        key="help_privacy",
        label="/help Privacy Shield",
        category="Commands",
        fallback="🔒",
        description="Privacy guarantee indicator in /help",
    ),
    "status_chart": EmojiSlot(
        key="status_chart",
        label="/status Chart Icon",
        category="Commands",
        fallback="📊",
        description="Header icon in admin /status telemetry",
    ),
    "status_ok": EmojiSlot(
        key="status_ok",
        label="/status Health OK",
        category="Commands",
        fallback="✅",
        description="Success indicator in /status stats",
    ),
    "status_fail": EmojiSlot(
        key="status_fail",
        label="/status Health Fail",
        category="Commands",
        fallback="❌",
        description="Failure indicator in /status stats",
    ),
    "report_success": EmojiSlot(
        key="report_success",
        label="/report Checkmark",
        category="Commands",
        fallback="✅",
        description="Feedback confirmation in /report command",
    ),
    "whoami_badge": EmojiSlot(
        key="whoami_badge",
        label="/whoami ID Badge",
        category="Commands",
        fallback="🆔",
        description="User ID icon in /whoami command",
    ),

    # System Alerts & Warnings
    "warning": EmojiSlot(
        key="warning",
        label="Warning / Limit Exceeded",
        category="Alerts",
        fallback="⚠️",
        description="Character limit exceeded and generic error warnings",
    ),
    "rate_limit": EmojiSlot(
        key="rate_limit",
        label="Rate Limit Cooldown",
        category="Alerts",
        fallback="⏳",
        description="Cooldown timer message when rate limit triggers",
    ),
    "unauthorized": EmojiSlot(
        key="unauthorized",
        label="Access Restricted",
        category="Alerts",
        fallback="🚫",
        description="Access denied indicator for unauthorized staff",
    ),
}

# In-memory fast cache
_slots_cache: dict[str, EmojiSlot] = {k: EmojiSlot(**asdict(v)) for k, v in DEFAULT_SLOTS.items()}
_initialized: bool = False


def get_emoji(slot_key: str) -> str:
    """Return HTML formatted <tg-emoji> tag if custom_emoji_id is set, else fallback emoji."""
    slot = _slots_cache.get(slot_key)
    if slot is None:
        default = DEFAULT_SLOTS.get(slot_key)
        return default.fallback if default else ""

    emoji_id = (slot.custom_emoji_id or "").strip()
    if emoji_id and emoji_id.isdigit():
        fallback = slot.fallback or "✨"
        if fallback == "→":
            fallback = "➡️"
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return slot.fallback


def get_custom_emoji_id(slot_key: str) -> str | None:
    """Return raw numeric custom_emoji_id string if configured, else None."""
    slot = _slots_cache.get(slot_key)
    if slot:
        cid = (slot.custom_emoji_id or "").strip()
        if cid and cid.isdigit():
            return cid
    return None


def get_slot_fallback(slot_key: str) -> str:
    """Return raw Unicode fallback emoji for slots used in buttons/plain-text."""
    slot = _slots_cache.get(slot_key)
    if slot and slot.fallback:
        return slot.fallback
    default = DEFAULT_SLOTS.get(slot_key)
    return default.fallback if default else ""


async def load_emoji_config() -> dict[str, EmojiSlot]:
    """Load emoji slots from database 'settings' table (key='bot_animated_emojis')."""
    global _initialized, _slots_cache
    from ..store import db as dbmod

    # Start with defaults
    merged: dict[str, EmojiSlot] = {k: EmojiSlot(**asdict(v)) for k, v in DEFAULT_SLOTS.items()}

    if dbmod.is_configured():
        try:
            from sqlalchemy import select
            from ..store.models import Setting

            async with dbmod.session() as sess:
                res = await sess.execute(
                    select(Setting).where(Setting.key == "bot_animated_emojis")
                )
                setting = res.scalar_one_or_none()
                if setting and setting.value and isinstance(setting.value.get("slots"), dict):
                    saved_slots = setting.value["slots"]
                    for k, val in saved_slots.items():
                        if k in merged and isinstance(val, dict):
                            custom_id = str(val.get("custom_emoji_id", "")).strip()
                            fallback = str(val.get("fallback", "")).strip() or merged[k].fallback
                            merged[k].custom_emoji_id = custom_id
                            merged[k].fallback = fallback
        except Exception as exc:
            log.warning("failed to load custom bot animated emojis from db: %s", exc)

    _slots_cache = merged
    _initialized = True
    return _slots_cache


async def save_emoji_config(slots_data: dict[str, Any]) -> dict[str, EmojiSlot]:
    """Save custom emoji configuration to database and immediately update cache."""
    global _slots_cache
    from ..store import db as dbmod
    from ..store.models import Setting
    from sqlalchemy import select

    # Merge into our slot definitions
    merged: dict[str, EmojiSlot] = {k: EmojiSlot(**asdict(v)) for k, v in DEFAULT_SLOTS.items()}

    to_store: dict[str, dict[str, str]] = {}
    for k, item in slots_data.items():
        if k in merged:
            custom_id = str(item.get("custom_emoji_id", "") if isinstance(item, dict) else item).strip()
            fallback = str(item.get("fallback", "") if isinstance(item, dict) else "").strip() or merged[k].fallback
            merged[k].custom_emoji_id = custom_id
            merged[k].fallback = fallback
            to_store[k] = {
                "custom_emoji_id": custom_id,
                "fallback": fallback,
            }

    if dbmod.is_configured():
        try:
            async with dbmod.session() as sess:
                res = await sess.execute(
                    select(Setting).where(Setting.key == "bot_animated_emojis")
                )
                setting = res.scalar_one_or_none()
                if setting is None:
                    setting = Setting(key="bot_animated_emojis", value={"slots": to_store})
                    sess.add(setting)
                else:
                    setting.value = {"slots": to_store}
                await sess.commit()
                log.info("saved animated emoji settings to database")
        except Exception as exc:
            log.error("failed to save animated emoji settings to database: %s", exc)

    _slots_cache = merged
    return _slots_cache


def get_all_slots() -> list[dict[str, Any]]:
    """Return all slot definitions with current state for Admin UI."""
    res = []
    for slot in _slots_cache.values():
        if slot.key == "copy_button":
            cid = (slot.custom_emoji_id or "").strip()
            if cid and cid.isdigit():
                preview = f"[Icon: {cid}] Copy"
            else:
                preview = f"{slot.fallback} Copy"
        else:
            preview = get_emoji(slot.key)
        res.append({
            "key": slot.key,
            "label": slot.label,
            "category": slot.category,
            "fallback": slot.fallback,
            "custom_emoji_id": slot.custom_emoji_id,
            "description": slot.description,
            "tag_preview": preview,
        })
    return res
