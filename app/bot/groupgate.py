"""Phase 0 group gate: private-DM access limited to GP members.

Private-chat requests are served ONLY when the sender is a member of the
ops group (GROUP_CHAT_ID). Membership is verified with Telegram's
getChatMember and cached per (group, user).

Cache lifetimes are asymmetric on purpose:
  allow verdicts -> GROUP_CACHE_TTL_S (default 6h; a leave takes effect
                    when it expires, an API call only every 6h per user)
  deny verdicts  -> GROUP_DENY_TTL_S (default 5 min; a freshly added member
                    gets in within minutes, not hours)

Decision table:
  TEST_ALLOW_ALL                                  -> allow (test mode)
  GROUP_CHAT_ID unset                             -> static allowlist only
  static allowlist hit (seeded staff/admin)       -> allow (admin override,
                                                     survives a group kick)
  fresh recheck requested (start_cmd=True)        -> skip cache, ask Telegram
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

from .. import config

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


def _ttl_for(decision: bool) -> int:
    """Allow verdicts live long; deny verdicts expire fast (quick join)."""
    if decision:
        return config.GROUP_CACHE_TTL_S or 6 * 3600
    return config.GROUP_DENY_TTL_S or 300


async def is_group_member(
    bot, cache, user_id: int, start_cmd: bool = False
) -> tuple[bool, str]:
    """Return (allowed, reason). Never raises - errors resolve to a verdict.

    start_cmd=True forces a fresh Telegram lookup (used by /start so a
    freshly added member never waits out a cached deny), then updates the
    cache with the new verdict.

    Reasons: test_mode | no_group_config | allowlist | member:<status> |
    non_member:<status> | stale_allow | stale_deny |
    error_deny:<ExceptionName>.
    """
    from ..store.userstore import UserStore

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

    cached_decision: bool | None = None
    cached_at = 0.0
    if not start_cmd:
        cached_decision, cached_at = _parse_cached(await cache.get_str(key))
        if cached_decision is not None:
            ttl = _ttl_for(cached_decision)
            if (time.time() - cached_at) < ttl:
                return cached_decision, ("member:cached" if cached_decision
                                         else "non_member:cached")
    else:
        # /start path: peek at the cache only as an error fallback, never
        # as an answer - a join must take effect immediately.
        cached_decision, cached_at = _parse_cached(await cache.get_str(key))

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

    await cache.set_str(key, f"{1 if verdict[0] else 0}:{time.time()}",
                        ex=_ttl_for(verdict[0]))
    return verdict


async def drop_cached_verdict(cache, user_id: int) -> None:
    """Forget one user's cached verdict (admin tooling / tests)."""
    if config.GROUP_CHAT_ID:
        await cache.delete(_cache_key(config.GROUP_CHAT_ID, user_id))
