"""Allowlist and per-user settings.

DB-backed when DATABASE_URL is set; otherwise an in-memory store seeded
from ALLOWED_USER_IDS / ADMIN_USER_IDS. TEST_ALLOW_ALL bypasses the
allowlist entirely (and grants admin for /status in test mode).

P1.4 hot-path memo: when DATABASE_URL is set, the three DB round trips
per message (is_allowed, get_target, daily_soft_cap) are memoized for
60 s in-process. Neon cold start therefore stops sitting in front of
every message. The memo is per-process and best-effort; admin changes
can be made visible immediately via invalidate() or after the TTL.
"""

from __future__ import annotations

import datetime
import logging
import time

from .. import config
from . import db as dbmod

log = logging.getLogger("opstranslate.users")

_MEMO_TTL_S = 60


class UserStore:
    def __init__(self) -> None:
        self._targets: dict[int, str] = {}  # in-memory fallback for user_settings
        self._seed_staff = set(config.ALLOWED_USER_IDS)
        self._seed_admin = set(config.ADMIN_USER_IDS)
        self._discovered_users: dict[int, dict] = {}  # in-memory discovered profile registry
        # 60 s memo caches: user_id -> (value, timestamp)
        self._allowed_memo: dict[int, tuple[tuple[bool, str], float]] = {}
        self._target_memo: dict[int, tuple[str, float]] = {}
        self._cap_memo: dict[int, tuple[int, float]] = {}

    # -- memo helpers -------------------------------------------------------
    def _memo_get(self, memo: dict, key: int):
        entry = memo.get(key)
        if entry is not None:
            val, ts = entry
            if (time.time() - ts) < _MEMO_TTL_S:
                return val
            # expired
            memo.pop(key, None)
        return None

    def _memo_set(self, memo: dict, key: int, value) -> None:
        memo[key] = (value, time.time())

    def invalidate(self, user_id: int) -> None:
        """Drop memo for one user (call after admin/role changes)."""
        self._allowed_memo.pop(user_id, None)
        self._target_memo.pop(user_id, None)
        self._cap_memo.pop(user_id, None)

    def invalidate_all(self) -> None:
        self._allowed_memo.clear()
        self._target_memo.clear()
        self._cap_memo.clear()

    async def is_allowed(self, user_id: int) -> tuple[bool, str]:
        """Return (allowed, role). Role is 'admin' | 'staff'."""
        if config.TEST_ALLOW_ALL:
            return True, "admin"  # test mode: everyone in, /status available

        # Memo only helps when DB is the source; without DB the lookup is
        # already in-memory via _seed_* sets.
        if dbmod.is_configured():
            memo_val = self._memo_get(self._allowed_memo, user_id)
            if memo_val is not None:
                return memo_val

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
                    result: tuple[bool, str] = (True, row.role or "staff")
                    self._memo_set(self._allowed_memo, user_id, result)
                    return result
                elif row is not None and not row.active:
                    result = (False, "suspended")
                    self._memo_set(self._allowed_memo, user_id, result)
                    return result
            except Exception as exc:  # noqa: BLE001 - fall through to env seed
                log.warning("allowlist_lookup_failed: %s", exc)

        # Check in-memory discovered users if suspended
        if hasattr(self, "_discovered_users") and user_id in self._discovered_users:
            rec = self._discovered_users[user_id]
            if not rec.get("active", True):
                result = (False, "suspended")
                self._memo_set(self._allowed_memo, user_id, result)
                return result

        # fallback to env seed
        if user_id in self._seed_admin:
            result = (True, "admin")
        elif user_id in self._seed_staff:
            result = (True, "staff")
        else:
            result = (False, "staff")
        # Also memoize seed result for 60 s so repeated calls do not
        # re-evaluate seed sets (cheap but consistent).
        self._memo_set(self._allowed_memo, user_id, result)
        return result

    async def get_target(self, user_id: int) -> str:
        # Memo first
        memo_val = self._memo_get(self._target_memo, user_id)
        if memo_val is not None:
            return memo_val

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
                    self._memo_set(self._target_memo, user_id, row.target_lang)
                    # keep _targets in sync for fallback
                    self._targets[user_id] = row.target_lang
                    return row.target_lang
            except Exception as exc:  # noqa: BLE001
                log.warning("target_lookup_failed: %s", exc)
                # fall through to in-memory fallback
        fallback = self._targets.get(user_id, "en")
        self._memo_set(self._target_memo, user_id, fallback)
        return fallback

    async def set_target(self, user_id: int, lang: str) -> None:
        self._targets[user_id] = lang
        # Invalidate memo so the next get_target sees the new value.
        self._target_memo.pop(user_id, None)
        self._memo_set(self._target_memo, user_id, lang)
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
        memo_val = self._memo_get(self._cap_memo, user_id)
        if memo_val is not None:
            return memo_val
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
                    cap = int(row.daily_soft_cap)
                    self._memo_set(self._cap_memo, user_id, cap)
                    return cap
            except Exception:  # noqa: BLE001
                pass
        cap = 200
        self._memo_set(self._cap_memo, user_id, cap)
        return cap

    async def sync_user_profile(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        username: str | None = None,
        auto_allow: bool = True,
    ) -> None:
        """Auto-discover or update a user's profile and last_active timestamp.

        Invoked when any user messages the bot.
        """
        if username:
            username = username.lstrip("@").strip()

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M")
        is_admin = user_id in self._seed_admin
        default_role = "admin" if is_admin else "staff"
        default_cap = 500 if is_admin else 200

        # 1. Update in-memory registry
        is_new = user_id not in self._discovered_users
        if is_new:
            self._discovered_users[user_id] = {
                "user_id": user_id,
                "display_name": full_name or f"User {user_id}",
                "username": username,
                "role": default_role,
                "daily_soft_cap": default_cap,
                "active": True if (auto_allow or is_admin) else False,
                "created_at": now_str,
                "last_active_at": now_iso,
            }
        else:
            rec = self._discovered_users[user_id]
            rec["last_active_at"] = now_iso
            if username:
                rec["username"] = username
            if full_name:
                rec["display_name"] = full_name

        # 2. Update/Insert in database if configured
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
                    if row is not None:
                        row.last_active_at = now_dt
                        if username:
                            row.username = username
                        if full_name:
                            row.display_name = full_name
                    else:
                        is_new = True
                        new_u = AllowedUser(
                            user_id=user_id,
                            display_name=full_name or f"User {user_id}",
                            username=username,
                            role=default_role,
                            daily_soft_cap=default_cap,
                            active=True if (auto_allow or is_admin) else False,
                            created_at=now_dt,
                            last_active_at=now_dt,
                        )
                        sess.add(new_u)
                    await sess.commit()
            except Exception as exc:  # noqa: BLE001
                log.warning("user_profile_sync_failed: %s", exc)

        # Invalidate memo
        self.invalidate(user_id)

        # Broadcast SSE if new user discovered
        if is_new:
            try:
                from ..admin.sse import broadcaster

                broadcaster.broadcast(
                    "users_changed",
                    {
                        "action": "auto_discover",
                        "user_id": user_id,
                        "display_name": full_name,
                        "username": username,
                    },
                )
            except Exception:  # noqa: BLE001
                pass

    def get_discovered_users(self) -> list[dict]:
        """Return in-memory discovered users (for dev or non-DB runs)."""
        return list(self._discovered_users.values())
