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


# ---------------------------------------------------------------------------
# Real aiogram ChatMember objects.
#
# The verdict logic must run against what Telegram actually returns:
# ChatMemberStatus is a str-mixed Enum, so str(status) is
# 'ChatMemberStatus.MEMBER' and not 'member'. The FakeMember tests above use
# plain strings and therefore cannot catch that - these cases can.
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402

from aiogram.types import (  # noqa: E402
    Chat,
    ChatMemberAdministrator,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberOwner,
    ChatMemberRestricted,
    ChatMemberUpdated,
    User,
)

from app.bot import handlers  # noqa: E402
from app.bot.groupgate import status_of  # noqa: E402
from app.services.alerts import AlertManager  # noqa: E402

_SUBJECT = User(id=41, is_bot=False, first_name="Real")


def _real_member(status: str, is_member: bool | None = None):
    """Build the real aiogram object Telegram would send for *status*."""
    if status == "member":
        return ChatMemberMember(chat_type="supergroup", user=_SUBJECT)
    if status == "administrator":
        return ChatMemberAdministrator(
            chat_type="supergroup", user=_SUBJECT, can_be_edited=True,
            is_anonymous=False, can_manage_chat=True, can_delete_messages=True,
            can_manage_video_chats=True, can_restrict_members=True,
            can_promote_members=False, can_change_info=True,
            can_invite_users=True, can_post_stories=True, can_edit_stories=True,
            can_delete_stories=True,
        )
    if status == "creator":
        return ChatMemberOwner(chat_type="supergroup", user=_SUBJECT,
                               is_anonymous=False)
    if status == "left":
        return ChatMemberLeft(chat_type="supergroup", user=_SUBJECT)
    if status == "kicked":
        return ChatMemberBanned(chat_type="supergroup", user=_SUBJECT,
                                until_date=datetime(2030, 1, 1,
                                                    tzinfo=timezone.utc))
    if status == "restricted":
        return ChatMemberRestricted(
            chat_type="supergroup", user=_SUBJECT, is_member=bool(is_member),
            can_send_messages=True, can_send_audios=True,
            can_send_documents=True, can_send_photos=True,
            can_send_videos=True, can_send_video_notes=True,
            can_send_voice_notes=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_change_info=True, can_invite_users=True, can_pin_messages=True,
            can_manage_topics=True,
            until_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
    raise ValueError(status)


def test_status_of_resolves_aiogram_enum():
    # str(ChatMemberStatus.MEMBER) == 'ChatMemberStatus.MEMBER' - the normaliser
    # must hand back the plain value or the gate denies every real member.
    assert status_of(_real_member("member")) == "member"
    assert status_of(_real_member("administrator")) == "administrator"
    assert status_of(_real_member("creator")) == "creator"
    assert status_of(_real_member("left")) == "left"
    assert status_of(_real_member("kicked")) == "kicked"
    assert status_of(FakeMember("member")) == "member"  # plain strings still work


class RealMemberBot:
    """Fake bot that returns REAL aiogram ChatMember objects."""

    def __init__(self, status, is_member=None):
        self._member = _real_member(status, is_member)
        self.calls = 0

    async def get_chat_member(self, chat_id, user_id):
        self.calls += 1
        return self._member


async def test_real_member_is_allowed():
    bot, cache = RealMemberBot("member"), Cache("")
    allowed, reason = await is_group_member(bot, cache, 41)
    assert allowed and reason == "member:member"
    assert bot.calls == 1


async def test_real_admin_and_owner_are_allowed():
    for status in ("administrator", "creator"):
        bot, cache = RealMemberBot(status), Cache("")
        allowed, reason = await is_group_member(bot, cache, 42)
        assert allowed, status
        assert reason == f"member:{status}"


async def test_real_restricted_member_allowed_stranger_denied():
    allowed, _ = await is_group_member(
        RealMemberBot("restricted", is_member=True), Cache(""), 43
    )
    assert allowed is True
    denied, reason = await is_group_member(
        RealMemberBot("restricted", is_member=False), Cache(""), 44
    )
    assert denied is False and reason == "non_member:restricted"


async def test_real_left_and_kicked_denied():
    for status in ("left", "kicked"):
        allowed, reason = await is_group_member(
            RealMemberBot(status), Cache(""), 45
        )
        assert not allowed and reason == f"non_member:{status}"


async def test_real_member_verdict_is_cached():
    # The cached allow must carry the resolved status, not the enum repr.
    bot, cache = RealMemberBot("member"), Cache("")
    await is_group_member(bot, cache, 46)
    allowed, reason = await is_group_member(bot, cache, 46)
    assert allowed and reason == "member:cached"
    assert bot.calls == 1


# ---------------------------------------------------------------------------
# Membership watchers: chat_member (other users) vs my_chat_member (the bot)
# ---------------------------------------------------------------------------

class FakeServices:
    """Duck-typed Services: the watchers only touch .cache and .alerts."""

    def __init__(self, cache=None):
        self.cache = cache or Cache("")
        self.alerts = AlertManager()
        self.sent: list[str] = []
        self.resolved: list[str] = []

        async def _capture_send(level, alert_type, component, detail, action):
            self.sent.append(alert_type)

        async def _capture_resolve(alert_type, component, detail):
            self.resolved.append(alert_type)

        self.alerts.send = _capture_send
        self.alerts.resolve = _capture_resolve


def _event_with_subject(subject_id: int, status: str, actor_id: int = 999,
                        chat_id: int = -100123456):
    """Build a ChatMemberUpdated whose SUBJECT is subject_id.

    _real_member hardcodes one user, so new_chat_member is rebuilt around the
    requested subject - the handler must read the subject, never the actor
    (event.from_user is the admin who made the change).
    """
    subject = User(id=subject_id, is_bot=False, first_name="Subject")
    # aiogram models are frozen pydantic instances: rebuild, never mutate.
    member = _real_member(status).model_copy(update={"user": subject})
    return ChatMemberUpdated(
        chat=Chat(id=chat_id, type="supergroup"),
        from_user=User(id=actor_id, is_bot=False, first_name="Admin"),
        date=datetime.now(timezone.utc),
        old_chat_member=_real_member("member"),
        new_chat_member=member,
    )


async def test_chat_member_kick_drops_subject_verdict():
    services = FakeServices()
    await services.cache.set_str("grp:-100123456:31", f"1:{time.time()}", ex=3600)
    await services.cache.set_str("grp:-100123456:999", f"1:{time.time()}", ex=3600)
    await handlers.on_group_membership_change(
        _event_with_subject(31, "kicked", actor_id=999), services
    )
    # The kicked member's cached allow verdict is gone...
    assert await services.cache.get_str("grp:-100123456:31") is None
    # ...and the admin who kicked them keeps theirs (subject, not actor).
    assert await services.cache.get_str("grp:-100123456:999") is not None


async def test_chat_member_kick_locks_the_door_immediately():
    # End to end: a cached allow must not survive the kick.
    bot, cache = FakeBot("member"), Cache("")
    services = FakeServices(cache)
    assert (await is_group_member(bot, cache, 51))[0] is True
    assert bot.calls == 1  # cached from here on
    await handlers.on_group_membership_change(
        _event_with_subject(51, "kicked"), services
    )
    bot._status = "kicked"
    allowed, reason = await is_group_member(bot, cache, 51)
    assert not allowed and reason == "non_member:kicked"
    assert bot.calls == 2  # re-verified instead of serving the stale allow


async def test_chat_member_join_clears_cached_deny():
    bot, cache = FakeBot("kicked"), Cache("")
    services = FakeServices(cache)
    assert (await is_group_member(bot, cache, 52))[0] is False
    await handlers.on_group_membership_change(
        _event_with_subject(52, "member"), services
    )
    bot._status = "member"
    allowed, reason = await is_group_member(bot, cache, 52)
    assert allowed and reason == "member:member"


async def test_chat_member_from_another_chat_is_ignored():
    services = FakeServices()
    await services.cache.set_str("grp:-100123456:61", f"1:{time.time()}", ex=3600)
    await handlers.on_group_membership_change(
        _event_with_subject(61, "kicked", chat_id=-100999999), services
    )
    assert await services.cache.get_str("grp:-100123456:61") is not None


async def test_watchers_are_registered_on_the_right_update_types():
    # chat_member = other users, my_chat_member = the bot itself. Registering
    # the user watcher on my_chat_member is the bug this test pins down.
    assert len(handlers.router.chat_member.handlers) == 1
    assert len(handlers.router.my_chat_member.handlers) == 1


async def test_bot_removed_from_group_alerts_and_returns_resolve():
    from app import main as app_main

    assert "chat_member" in app_main.ALLOWED_UPDATES
    services = FakeServices()
    bot_user = User(id=7, is_bot=True, first_name="Bot")
    event = ChatMemberUpdated(
        chat=Chat(id=-100123456, type="supergroup"),
        from_user=User(id=999, is_bot=False, first_name="Admin"),
        date=datetime.now(timezone.utc),
        old_chat_member=ChatMemberMember(chat_type="supergroup", user=bot_user),
        new_chat_member=ChatMemberLeft(chat_type="supergroup", user=bot_user),
    )
    await handlers.on_bot_membership_change(event, services)
    assert services.sent == ["GROUP_GATE_UNAVAILABLE"]

    back = ChatMemberUpdated(
        chat=Chat(id=-100123456, type="supergroup"),
        from_user=User(id=999, is_bot=False, first_name="Admin"),
        date=datetime.now(timezone.utc),
        old_chat_member=ChatMemberLeft(chat_type="supergroup", user=bot_user),
        new_chat_member=ChatMemberAdministrator(
            chat_type="supergroup", user=bot_user, can_be_edited=True,
            is_anonymous=False, can_manage_chat=True, can_delete_messages=True,
            can_manage_video_chats=True, can_restrict_members=True,
            can_promote_members=False, can_change_info=True,
            can_invite_users=True, can_post_stories=True, can_edit_stories=True,
            can_delete_stories=True,
        ),
    )
    await handlers.on_bot_membership_change(back, services)
    assert services.resolved == ["GROUP_GATE_UNAVAILABLE"]
