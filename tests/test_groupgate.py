"""Tests for the Phase 0 group gate: private-DM + GP-member-only access.

The gate consults Telegram's getChatMember and caches the verdict, so the
fake bot records every API call - the caching tests assert the call count.
"""
import time

import pytest

from app import config
from app.services.cache import Cache
from app.bot.groupgate import is_group_member


class FakeMember:
    def __init__(self, status, is_member=False):
        self.status = status
        self.is_member = is_member


class FakeBot:
    def __init__(self, status="member", fail=False):
        self._status = status
        self.fail = fail
        self.calls = 0

    async def get_chat_member(self, chat_id, user_id):
        self.calls += 1
        if self.fail:
            raise RuntimeError("telegram down")
        if self._status == "restricted-member":
            return FakeMember("restricted", is_member=True)
        if self._status == "restricted-stranger":
            return FakeMember("restricted", is_member=False)
        return FakeMember(self._status)


@pytest.fixture(autouse=True)
def _group_env(monkeypatch):
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", False)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456)
    monkeypatch.setattr(config, "GROUP_CACHE_TTL_S", 3600)
    monkeypatch.setattr(config, "GROUP_DENY_TTL_S", 300)
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [])


async def test_member_allowed():
    bot, cache = FakeBot("member"), Cache("")
    allowed, reason = await is_group_member(bot, cache, 11)
    assert allowed and reason == "member:member"
    assert bot.calls == 1


async def test_admin_creator_allowed():
    for status in ("administrator", "creator"):
        bot, cache = FakeBot(status), Cache("")
        allowed, _ = await is_group_member(bot, cache, 12)
        assert allowed, status


async def test_left_kicked_denied():
    for status in ("left", "kicked"):
        bot, cache = FakeBot(status), Cache("")
        allowed, reason = await is_group_member(bot, cache, 13)
        assert not allowed and reason == f"non_member:{status}"


async def test_restricted_member_allowed_stranger_denied():
    bot, cache = FakeBot("restricted-member"), Cache("")
    assert (await is_group_member(bot, cache, 14))[0] is True
    bot2, cache2 = FakeBot("restricted-stranger"), Cache("")
    allowed, _ = await is_group_member(bot2, cache2, 15)
    assert allowed is False


async def test_verdict_cached_no_second_api_call():
    bot, cache = FakeBot("member"), Cache("")
    await is_group_member(bot, cache, 16)
    allowed, reason = await is_group_member(bot, cache, 16)
    assert allowed and reason == "member:cached"
    assert bot.calls == 1  # second check served from cache


async def test_deny_cached_too():
    bot, cache = FakeBot("kicked"), Cache("")
    await is_group_member(bot, cache, 17)
    allowed, reason = await is_group_member(bot, cache, 17)
    assert not allowed and reason == "non_member:cached"
    assert bot.calls == 1


async def test_stale_cache_used_when_api_down():
    bot, cache = FakeBot("member"), Cache("")
    await is_group_member(bot, cache, 18)
    # Age the entry past the TTL so the next check must re-verify, then the
    # API fails: the stale allow verdict is reused instead of failing closed.
    raw = await cache.get_str("grp:-100123456:18")
    verdict = raw.partition(":")[0]
    await cache.set_str("grp:-100123456:18", f"{verdict}:{time.time() - 7200}", ex=60)
    bot.fail = True
    allowed, reason = await is_group_member(bot, cache, 18)
    assert allowed and reason == "stale_allow"


async def test_error_without_cache_denies_fail_closed():
    bot, cache = FakeBot(fail=True), Cache("")
    allowed, reason = await is_group_member(bot, cache, 19)
    assert not allowed and reason.startswith("error_deny")


async def test_allowlist_override_survives_kick(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [20])
    bot, cache = FakeBot("kicked"), Cache("")
    allowed, reason = await is_group_member(bot, cache, 20)
    assert allowed and reason == "allowlist"
    assert bot.calls == 0  # never even asked Telegram


async def test_test_mode_bypasses_everything(monkeypatch):
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", True)
    bot, cache = FakeBot("kicked"), Cache("")
    allowed, reason = await is_group_member(bot, cache, 21)
    assert allowed and reason == "test_mode"
    assert bot.calls == 0


async def test_no_group_config_falls_back_to_allowlist(monkeypatch):
    monkeypatch.setattr(config, "GROUP_CHAT_ID", 0)
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [22])
    bot, cache = FakeBot("member"), Cache("")
    allowed, _ = await is_group_member(bot, cache, 22)
    assert allowed and bot.calls == 0
    denied, _ = await is_group_member(bot, cache, 23)
    assert denied is False


async def test_expired_cache_refetches(monkeypatch):
    monkeypatch.setattr(config, "GROUP_CACHE_TTL_S", 1)
    bot, cache = FakeBot("member"), Cache("")
    await is_group_member(bot, cache, 24)
    assert bot.calls == 1
    # Age the entry past the 1s TTL by rewriting it with an old timestamp.
    raw = await cache.get_str("grp:-100123456:24")
    verdict, _ = raw.partition(":")[0], None
    await cache.set_str("grp:-100123456:24", f"{verdict}:{time.time() - 10}", ex=60)
    await is_group_member(bot, cache, 24)
    assert bot.calls == 2


async def test_deny_expires_fast_allow_lasts_long():
    # A deny verdict expires after GROUP_DENY_TTL_S, so a join takes
    # effect within minutes; an allow verdict keeps the long TTL.
    bot, cache = FakeBot("kicked"), Cache("")
    await is_group_member(bot, cache, 25)
    assert bot.calls == 1
    raw = await cache.get_str("grp:-100123456:25")
    verdict = raw.partition(":")[0]
    # 6 minutes old: past the 5-min deny TTL -> must re-verify.
    await cache.set_str("grp:-100123456:25", f"{verdict}:{time.time() - 360}", ex=60)
    bot._status = "member"  # user joined the group since the deny
    allowed, reason = await is_group_member(bot, cache, 25)
    assert allowed and reason == "member:member"
    assert bot.calls == 2


async def test_start_cmd_forces_fresh_lookup():
    # /start skips the cache: a cached deny from before the join must not
    # block the first /start after joining.
    bot, cache = FakeBot("kicked"), Cache("")
    await is_group_member(bot, cache, 26)
    assert bot.calls == 1
    bot._status = "member"
    allowed, reason = await is_group_member(bot, cache, 26, start_cmd=True)
    assert allowed and reason == "member:member"
    assert bot.calls == 2


async def test_start_cmd_falls_back_to_stale_on_error():
    bot, cache = FakeBot("member"), Cache("")
    await is_group_member(bot, cache, 27)
    bot.fail = True
    allowed, reason = await is_group_member(bot, cache, 27, start_cmd=True)
    assert allowed and reason == "stale_allow"
