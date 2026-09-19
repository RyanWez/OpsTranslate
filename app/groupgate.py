"""Phase 0 group gate: private-DM access limited to GP members.

Private-chat requests are served ONLY when the sender is a member of the
ops group (GROUP_CHAT_ID). Membership is verified with Telegram's
getChatMember and cached per (group, user) for GROUP_CACHE_TTL_S so a
message does not cost an extra API call.

Decision table:
  TEST_ALLOW_ALL                                  -> allow (test mode)
  GROUP_CHAT_ID unset                             -> static allowlist only
  static allowlist hit (seeded staff/admin)       -> allow (admin override,
                                                     survives a group kick)
  getChatMember -> member/administrator/creator   -> allow
  getChatMember -> restricted (is_member=True)    -> allow
  getChatMember -> left/kicked/restricted         -> deny (silent drop)
  API error + stale cache present                 -> stale decision (fail-open
                                                     within TTL, not forever)
  API error + no cache                            -> deny (fail closed: money
                                                     must never leak)

Fail-closed on error is deliberate: an unverified user must never reach
Gate 10 (the only gate that costs provider money).
"""
from __future__ import annotations

import logging
import time

from . import config

log = logging.getLogger("opstranslate.groupgate")

_MEMBER_STATUSES = ("creator", "owner", "administrator", "member")


def _cache_key(group_id: int, user_id: int) -> str:
    return f"grp:{group_id}:{user_id}"


def _parse_cached(raw: str | None) -> tuple[bool | None, float]:
    """Decode a cached verdict: '1:<ts>' allow, '0:<ts>' deny, else miss."""
    if not raw:
        return None, 0.0
    verdict, _, ts = raw.partition(":")
    try:
        return (verdict == "1"), float(ts)
    except ValueError:
        return None, 0.0


async def is_group_member(bot, cache, user_id: int) -> tuple[bool, str]:
    """Return (allowed, reason). Never raises - errors resolve to a verdict.

    Reasons: test_mode | no_group_config | allowlist | member:<status> |
    non_member:<status> | stale_allow | stale_deny |
    error_deny:<ExceptionName>.
    """
    from .userstore import UserStore  # deferred: avoids a circular import

    if config.TEST_ALLOW_ALL:
        return True, "test_mode"

    group_id = config.GROUP_CHAT_ID
    if not group_id:
        # Gate not configured: the static allowlist is the only control.
        allowed, role = await UserStore().is_allowed(user_id)
        return allowed, f"no_group_config:{role}"

    # Admin override first: static staff/admin survive a group kick so the
    # owner is never locked out by a membership mistake.
    allowed, _ = await UserStore().is_allowed(user_id)
    if allowed:
        return True, "allowlist"

    key = _cache_key(group_id, user_id)
    ttl = config.GROUP_CACHE_TTL_S or 6 * 3600
    cached_decision, cached_at = _parse_cached(await cache.get_str(key))
    fresh = cached_decision is not None and (time.time() - cached_at) < ttl
    if fresh:
        assert cached_decision is not None
        return cached_decision, ("member:cached" if cached_decision
                                 else "non_member:cached")

    try:
        member = await bot.get_chat_member(chat_id=group_id, user_id=user_id)
        status = str(getattr(member, "status", "") or "").lower()
    except Exception as exc:  # noqa: BLE001 - fail closed unless stale cache
        log.warning("group_lookup_failed user=%s: %s", user_id, exc)
        if cached_decision is not None:
            return cached_decision, ("stale_allow" if cached_decision
                                     else "stale_deny")
        return False, f"error_deny:{type(exc).__name__}"

    if status in _MEMBER_STATUSES:
        verdict: tuple[bool, str] = (True, f"member:{status}")
    elif status == "restricted":
        verdict = (bool(getattr(member, "is_member", False)),
                   f"member:restricted"
                   if getattr(member, "is_member", False)
                   else "non_member:restricted")
    else:  # left, kicked, unknown strings: not a member.
        verdict = (False, f"non_member:{status or 'unknown'}")

    await cache.set_str(key, f"{1 if verdict[0] else 0}:{time.time()}", ex=ttl)
    return verdict
