"""Allowlist and per-user settings.

DB-backed when DATABASE_URL is set; otherwise an in-memory store seeded
from ALLOWED_USER_IDS / ADMIN_USER_IDS. TEST_ALLOW_ALL bypasses the
allowlist entirely (and grants admin for /status in test mode).
"""
from __future__ import annotations

import logging

from . import config
from . import db as dbmod

log = logging.getLogger("opstranslate.users")


class UserStore:
    def __init__(self) -> None:
        self._targets: dict[int, str] = {}  # in-memory fallback for user_settings
        self._seed_staff = set(config.ALLOWED_USER_IDS)
        self._seed_admin = set(config.ADMIN_USER_IDS)

    async def is_allowed(self, user_id: int) -> tuple[bool, str]:
        """Return (allowed, role). Role is 'admin' | 'staff'."""
        if config.TEST_ALLOW_ALL:
            return True, "admin"  # test mode: everyone in, /status available
        if dbmod.is_configured():
            try:
                from sqlalchemy import select

                from .models import AllowedUser

                async with dbmod.session() as sess:
                    row = (
                        await sess.execute(
                            select(AllowedUser).where(AllowedUser.user_id == user_id)
                        )
                    ).scalar_one_or_none()
                if row is not None and row.active:
                    return True, row.role or "staff"
                return False, "staff"
            except Exception as exc:  # noqa: BLE001 - fail closed on DB errors
                log.warning("allowlist_lookup_failed: %s", exc)
                return False, "staff"
        if user_id in self._seed_admin:
            return True, "admin"
        if user_id in self._seed_staff:
            return True, "staff"
        return False, "staff"

    async def get_target(self, user_id: int) -> str:
        if dbmod.is_configured():
            try:
                from sqlalchemy import select

                from .models import UserSettings

                async with dbmod.session() as sess:
                    row = (
                        await sess.execute(
                            select(UserSettings).where(UserSettings.user_id == user_id)
                        )
                    ).scalar_one_or_none()
                if row is not None:
                    return row.target_lang
            except Exception as exc:  # noqa: BLE001
                log.warning("target_lookup_failed: %s", exc)
        return self._targets.get(user_id, "en")

    async def set_target(self, user_id: int, lang: str) -> None:
        self._targets[user_id] = lang
        if dbmod.is_configured():
            try:
                from sqlalchemy import select

                from .models import UserSettings

                async with dbmod.session() as sess:
                    row = (
                        await sess.execute(
                            select(UserSettings).where(UserSettings.user_id == user_id)
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        sess.add(UserSettings(user_id=user_id, target_lang=lang))
                    else:
                        row.target_lang = lang
                    await sess.commit()
            except Exception as exc:  # noqa: BLE001
                log.warning("target_save_failed: %s", exc)

    async def daily_soft_cap(self, user_id: int) -> int:
        if dbmod.is_configured():
            try:
                from sqlalchemy import select

                from .models import AllowedUser

                async with dbmod.session() as sess:
                    row = (
                        await sess.execute(
                            select(AllowedUser).where(AllowedUser.user_id == user_id)
                        )
                    ).scalar_one_or_none()
                if row is not None and row.daily_soft_cap:
                    return row.daily_soft_cap
            except Exception:  # noqa: BLE001
                pass
        return 200
