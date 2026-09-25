"""Handler level: the spec section 03 input-resolution table, the commands,
and the Phase 0 access gate in front of all of them.

`on_text` / `cmd_tr` are called directly (aiogram's decorators register the
function unchanged), so these tests describe the routing rules without
running a dispatcher.
"""
import pytest
from types import SimpleNamespace

from app import config
from app.bot import handlers, strings
from app.services import ratelimit

from .fakes import FakeBot, FakeMessage, StubRouter, StubUserStore, make_services

USER = 11
CHAT = 11
BOT_ID = 777


@pytest.fixture(autouse=True)
def _open_gate(monkeypatch):
    """Bypass the group gate by default - it has its own 27 tests."""
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", True)
    handlers._bot_id_cache.clear()
    ratelimit.reset()          # the sliding window is process-global
    from app.services import maintenance
    from app.services.maintenance import MaintenanceConfig
    import time
    maintenance._cached = MaintenanceConfig(enabled=False)
    maintenance._cached_at = time.monotonic() + 999999
    yield
    handlers._bot_id_cache.clear()
    ratelimit.reset()
    maintenance.invalidate_cache()


def services_with(bot=None, router=None, **kw):
    return make_services(bot or FakeBot(me_id=BOT_ID),
                         router or StubRouter(["User ID is wrong"]), **kw)


# ---------------------------------------------------------------------------
# Section 03 - input resolution: what gets translated, and anchored to what
# ---------------------------------------------------------------------------

async def test_plain_message_translates_itself_anchored_to_itself():
    bot, router = FakeBot(me_id=BOT_ID), StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    msg = FakeMessage(message_id=31, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်")

    await handlers.on_text(msg, services, bot)
    assert bot.sent[0].reply_to == 31
    assert "User ID is wrong" in bot.last_text()


async def test_plain_reply_translates_the_new_message_not_the_quoted_one():
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    quoted = FakeMessage(message_id=20, text="ignored quoted text", from_id=99)
    msg = FakeMessage(message_id=32, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်", reply_to=quoted)

    await handlers.on_text(msg, services, bot)
    assert bot.sent[0].reply_to == 32          # anchored to the NEW message
    assert router.masked and "ignored quoted text" not in router.masked[0]


async def test_tr_as_a_reply_translates_the_replied_to_message():
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    replied = FakeMessage(message_id=21, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်", from_id=99)
    msg = FakeMessage(message_id=33, text="/tr", reply_to=replied)

    await handlers.cmd_tr(msg, services, bot)
    assert bot.sent[0].reply_to == 21          # anchored to the replied-to one
    assert "User ID is wrong" in bot.last_text()


async def test_tr_with_inline_text_translates_the_text_after_the_command():
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    msg = FakeMessage(message_id=34, text="/tr ဂိမ်းအိုင်ဒီ မှားနေတယ်")

    await handlers.cmd_tr(msg, services, bot)
    assert bot.sent[0].reply_to == 34
    assert "ဂိမ်း" not in router.masked[0]     # the text after /tr was used


async def test_tr_at_the_bot_username_is_stripped():
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    msg = FakeMessage(message_id=35, text="/tr@OpsTranslateBot ဂိမ်းအိုင်ဒီ စစ်ပေး")

    await handlers.cmd_tr(msg, services, bot)
    assert router.calls == 1


async def test_bare_tr_replies_with_the_auto_mode_notice():
    bot, router = FakeBot(me_id=BOT_ID), StubRouter()
    services = services_with(bot, router)
    msg = FakeMessage(message_id=36, text="/tr")

    await handlers.cmd_tr(msg, services, bot)
    assert msg.answers == [strings.AUTO_MODE]
    assert router.calls == 0


async def test_forwarded_text_is_translated_like_any_other():
    # A forwarded message arrives with .text set; there is no special case,
    # and the output is anchored to the forwarded copy (spec 03, row 5).
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    msg = FakeMessage(message_id=37, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်")
    msg.forward_origin = SimpleNamespace(chat=SimpleNamespace(id=4242))

    await handlers.on_text(msg, services, bot)
    assert bot.sent[0].reply_to == 37
    assert router.calls == 1


async def test_reply_to_a_bot_message_is_already_translated():
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter()
    services = services_with(bot, router)
    bot_message = FakeMessage(message_id=22, text="The user ID is wrong.",
                              from_id=BOT_ID)
    msg = FakeMessage(message_id=38, text="ok", reply_to=bot_message)

    await handlers.on_text(msg, services, bot)
    assert msg.replies == [strings.ALREADY_TRANSLATED]
    assert router.calls == 0                   # stateless: no re-translation


async def test_caption_is_translated():
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router)
    msg = FakeMessage(message_id=39, text=None, caption="ဂိမ်းအိုင်ဒီ မှားနေတယ်")

    await handlers.on_text(msg, services, bot)
    assert "User ID is wrong" in bot.last_text()


async def test_blank_caption_gets_the_unsupported_type_reply():
    bot, router = FakeBot(me_id=BOT_ID), StubRouter()
    services = services_with(bot, router)
    msg = FakeMessage(message_id=40, text=None, caption="   ")

    await handlers.on_text(msg, services, bot)
    assert msg.replies == [strings.UNSUPPORTED_TYPE]
    assert router.calls == 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def test_start_sends_welcome_and_seeds_the_fallback_target():
    bot = FakeBot(me_id=BOT_ID)
    users = StubUserStore(target="my")
    services = services_with(bot, user_store=users)
    msg = FakeMessage(message_id=41, text="/start")

    await handlers.cmd_start(msg, services)
    assert msg.answers == [strings.WELCOME]
    assert users.targets_set == [(USER, "en")]   # stored target = fallback only


async def test_help_sends_the_usage_card():
    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot)
    msg = FakeMessage(message_id=42, text="/help")

    await handlers.cmd_help(msg, services)
    assert msg.answers == [strings.HELP]


async def test_whoami_reports_the_callers_own_id():
    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot)
    msg = FakeMessage(message_id=43, text="/whoami", from_id=987654)

    await handlers.cmd_whoami(msg, services)
    assert "Your Telegram user ID:" in msg.answers[0] and "987654" in msg.answers[0]


async def test_whoami_works_for_non_members_and_only_in_private(monkeypatch):
    # Spec v3.1(2): exempt from the gate, otherwise onboarding is impossible.
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", False)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456)
    bot = FakeBot(me_id=BOT_ID, member_status="left")   # a stranger
    services = services_with(bot, user_store=StubUserStore(allowed=False))

    msg = FakeMessage(message_id=44, text="/whoami", from_id=555)
    await handlers.cmd_whoami(msg, services)
    assert "Your Telegram user ID:" in msg.answers[0] and "555" in msg.answers[0]

    group_msg = FakeMessage(message_id=45, text="/whoami", chat_type="supergroup",
                            chat_id=-100123456, from_id=555)
    await handlers.cmd_whoami(group_msg, services)
    assert group_msg.answers == []


async def test_status_is_admin_only(monkeypatch):
    # TEST_ALLOW_ALL deliberately grants admin, so turn it off to see the
    # role check itself.
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", False)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456)
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    bot = FakeBot(me_id=BOT_ID, member_status="member")   # past the gate...
    services = services_with(bot, user_store=StubUserStore(role="staff"))
    msg = FakeMessage(message_id=46, text="/status")
    await handlers.cmd_status(msg, services)
    assert msg.answers == []                   # staff: silent

    admin = services_with(bot, user_store=StubUserStore(role="admin"))
    msg2 = FakeMessage(message_id=47, text="/status")
    await handlers.cmd_status(msg2, admin)
    assert len(msg2.answers) == 1
    body = msg2.answers[0]
    assert "Status" in body
    assert "Policy: v1" in body
    assert "Providers:" in body and "- none" in body


# ---------------------------------------------------------------------------
# Phase 0 gate in front of everything
# ---------------------------------------------------------------------------

async def test_non_member_gets_nothing_at_all(monkeypatch):
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", False)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456)
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [])
    bot = FakeBot(me_id=BOT_ID, member_status="left")
    router = StubRouter()
    services = services_with(bot, router, user_store=StubUserStore(allowed=False))
    msg = FakeMessage(message_id=48, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်")

    await handlers.on_text(msg, services, bot)
    assert bot.calls == []                     # invisible: no placeholder, no error
    assert msg.replies == [] and msg.answers == []
    assert router.calls == 0


async def test_group_chat_updates_are_ignored(monkeypatch):
    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter()
    services = services_with(bot, router)
    msg = FakeMessage(message_id=49, text="hello", chat_type="supergroup",
                      chat_id=-100123456)

    await handlers.on_text(msg, services, bot)
    assert bot.calls == [] and router.calls == 0


async def test_group_member_is_served(monkeypatch):
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", False)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456)
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    bot = FakeBot(me_id=BOT_ID, member_status="member")
    router = StubRouter(["User ID is wrong"])
    services = services_with(bot, router, user_store=StubUserStore(allowed=False))
    msg = FakeMessage(message_id=50, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်")

    await handlers.on_text(msg, services, bot)
    assert router.calls == 1


# ---------------------------------------------------------------------------
# Language-button callback (the v3.2 stored-target fallback)
# ---------------------------------------------------------------------------

class FakeCallback:
    def __init__(self, data="lang:my", from_id=USER):
        self.data = data
        self.from_user = SimpleNamespace(id=from_id)
        self.answers: list[str] = []
        self.edits: list[str] = []
        self.message = SimpleNamespace(edit_text=self._edit)

    async def answer(self, text="", **kw):
        self.answers.append(text)

    async def _edit(self, text, **kw):
        self.edits.append(text)


async def test_lang_button_sets_the_fallback_target():
    bot = FakeBot(me_id=BOT_ID)
    users = StubUserStore(target="en")
    services = services_with(bot, user_store=users)
    call = FakeCallback("lang:my")

    await handlers.cb_lang(call, services)
    assert users.targets_set == [(USER, "my")]
    assert call.answers == [strings.TARGET_SET.format(LANG="Myanmar")]
    assert call.edits == [strings.TARGET_SET.format(LANG="Myanmar")]


async def test_lang_button_rejects_unknown_codes():
    bot = FakeBot(me_id=BOT_ID)
    users = StubUserStore()
    services = services_with(bot, user_store=users)
    call = FakeCallback("lang:zh")

    await handlers.cb_lang(call, services)
    assert call.answers == ["Unknown language."]
    assert users.targets_set == []


async def test_lang_button_is_dismissed_for_non_members(monkeypatch):
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", False)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456)
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    bot = FakeBot(me_id=BOT_ID, member_status="kicked")
    users = StubUserStore(allowed=False)
    services = services_with(bot, user_store=users)
    call = FakeCallback("lang:my")

    await handlers.cb_lang(call, services)
    assert call.answers == [""]                # spinner dismissed...
    assert users.targets_set == []             # ...and nothing changed


async def test_cmd_report_sends_alert():
    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot)
    reply_to = FakeMessage(message_id=99, text="Some translation output")
    msg = FakeMessage(message_id=100, text="/report wrong terms used", reply_to=reply_to)

    await handlers.cmd_report(msg, services)
    assert any("Feedback received" in rep for rep in msg.replies)
    assert any(a[1] == "TRANSLATION_REPORT" for a in services.alerts.sent)

