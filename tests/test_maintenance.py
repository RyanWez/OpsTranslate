"""Tests for Maintenance Mode behavior and Admin Bypass."""
import time
import pytest
from app import config
from app.bot import handlers
from app.services import maintenance
from app.services.maintenance import MaintenanceConfig
from app.store.userstore import UserStore

from .fakes import FakeBot, FakeMessage, StubRouter, StubUserStore, make_services

ADMIN_ID = 8777968077
STAFF_ID = 7672856636
BOT_ID = 777


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [ADMIN_ID])
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", True)
    monkeypatch.setattr(config, "GROUP_CHAT_ID", 0)
    monkeypatch.setattr("app.store.db.is_configured", lambda: False)
    handlers._bot_id_cache.clear()
    maintenance.invalidate_cache()
    yield
    handlers._bot_id_cache.clear()
    maintenance.invalidate_cache()


def set_maintenance_state(monkeypatch, cfg: MaintenanceConfig):
    async def _fake_cfg(*args, **kw):
        return cfg
    monkeypatch.setattr(maintenance, "get_config", _fake_cfg)
    monkeypatch.setattr(handlers, "get_maintenance_config", _fake_cfg)
    maintenance._cached = cfg
    maintenance._cached_at = time.monotonic()


def services_with(bot=None, router=None, **kw):
    return make_services(
        bot or FakeBot(me_id=BOT_ID),
        router or StubRouter(["Hello translated"]),
        **kw
    )


@pytest.mark.asyncio
async def test_userstore_test_allow_all_grants_staff_not_admin(monkeypatch):
    """TEST_ALLOW_ALL must grant 'staff' role to unknown users, NOT 'admin'."""
    monkeypatch.setattr(config, "TEST_ALLOW_ALL", True)
    store = UserStore()
    allowed, role = await store.is_allowed(123456789)
    assert allowed is True
    assert role == "staff"

    # Seeded admin still gets admin
    allowed, role = await store.is_allowed(ADMIN_ID)
    assert allowed is True
    assert role == "admin"


@pytest.mark.asyncio
async def test_maintenance_blocks_staff_when_enabled(monkeypatch):
    """When maintenance is ON, staff users are blocked with custom maintenance message."""
    cfg = MaintenanceConfig(enabled=True, allow_admin_bypass=True, message="Bot under maintenance test")
    set_maintenance_state(monkeypatch, cfg)

    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot, user_store=StubUserStore(role="staff"))
    msg = FakeMessage(message_id=101, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်", from_id=STAFF_ID)

    await handlers.on_text(msg, services, bot)
    assert len(msg.answers) == 1
    assert "Bot under maintenance test" in msg.answers[0]
    # No translation sent
    assert bot.sent == []


@pytest.mark.asyncio
async def test_maintenance_admin_bypass_enabled(monkeypatch):
    """When maintenance is ON and allow_admin_bypass=True, admin bypasses and gets warning banner."""
    cfg = MaintenanceConfig(enabled=True, allow_admin_bypass=True, message="Bot under maintenance test")
    set_maintenance_state(monkeypatch, cfg)

    bot = FakeBot(me_id=BOT_ID)
    router = StubRouter(["Admin bypass translation"])
    services = services_with(bot, router, user_store=StubUserStore(role="admin"))
    msg = FakeMessage(message_id=102, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်", from_id=ADMIN_ID)

    await handlers.on_text(msg, services, bot)
    # Admin is not blocked
    assert msg.answers == []
    # Translation delivered with Admin Bypass indicator
    last_text = bot.last_text()
    assert "Admin bypass translation" in last_text
    assert "Maintenance Mode — Admin Bypass" in last_text


@pytest.mark.asyncio
async def test_maintenance_admin_blocked_when_bypass_disabled(monkeypatch):
    """When maintenance is ON and allow_admin_bypass=False, admin is ALSO blocked."""
    cfg = MaintenanceConfig(enabled=True, allow_admin_bypass=False, message="Full maintenance shutdown")
    set_maintenance_state(monkeypatch, cfg)

    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot, user_store=StubUserStore(role="admin"))
    msg = FakeMessage(message_id=103, text="ဂိမ်းအိုင်ဒီ မှားနေတယ်", from_id=ADMIN_ID)

    await handlers.on_text(msg, services, bot)
    assert len(msg.answers) == 1
    assert "Full maintenance shutdown" in msg.answers[0]
    assert bot.sent == []


@pytest.mark.asyncio
async def test_status_displays_maintenance_active(monkeypatch):
    """Admin /status command displays maintenance status."""
    cfg = MaintenanceConfig(enabled=True, allow_admin_bypass=True)
    set_maintenance_state(monkeypatch, cfg)

    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot, user_store=StubUserStore(role="admin"))
    msg = FakeMessage(message_id=104, text="/status", from_id=ADMIN_ID)

    await handlers.cmd_status(msg, services)
    assert len(msg.answers) == 1
    body = msg.answers[0]
    assert "Maintenance: <b>ACTIVE</b> (Admin Bypass: ON)" in body


@pytest.mark.asyncio
async def test_status_displays_maintenance_inactive(monkeypatch):
    """Admin /status command displays maintenance inactive when disabled."""
    cfg = MaintenanceConfig(enabled=False)
    set_maintenance_state(monkeypatch, cfg)

    bot = FakeBot(me_id=BOT_ID)
    services = services_with(bot, user_store=StubUserStore(role="admin"))
    msg = FakeMessage(message_id=105, text="/status", from_id=ADMIN_ID)

    await handlers.cmd_status(msg, services)
    assert len(msg.answers) == 1
    body = msg.answers[0]
    assert "Maintenance: Inactive" in body


@pytest.mark.asyncio
async def test_maintenance_uses_animated_emoji_when_configured(monkeypatch):
    """When a custom animated emoji is configured for maintenance, it upgrades 🔧 in the text."""
    from app.bot import emojis, strings
    emojis._slots_cache["maintenance"].custom_emoji_id = "54321987654321"
    try:
        text = strings.maintenance_text()
        assert '<tg-emoji emoji-id="54321987654321">🔧</tg-emoji>' in text

        custom_text = "🔧 <b>Custom maintenance title</b>\nPlease wait."
        rendered = strings.maintenance_text(custom_text)
        assert '<tg-emoji emoji-id="54321987654321">🔧</tg-emoji>' in rendered
    finally:
        emojis._slots_cache["maintenance"].custom_emoji_id = ""


@pytest.mark.asyncio
async def test_broadcast_maintenance_notification_on(monkeypatch):
    """Broadcasting ON delivers the update notice to configured recipients."""
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [ADMIN_ID])
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [STAFF_ID])
    bot = FakeBot(me_id=BOT_ID)

    sent_count = await maintenance.broadcast_maintenance_notification(
        bot,
        enabled=True,
        custom_message="Database migration in progress",
    )
    assert sent_count == 2
    assert len(bot.sent) == 2
    chat_ids = {c.chat_id for c in bot.sent}
    assert chat_ids == {ADMIN_ID, STAFF_ID}
    for call in bot.sent:
        assert "Database migration in progress" in call.text


@pytest.mark.asyncio
async def test_broadcast_maintenance_notification_off(monkeypatch):
    """Broadcasting OFF delivers the service resumed notice to configured recipients."""
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [ADMIN_ID])
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [STAFF_ID])
    bot = FakeBot(me_id=BOT_ID)

    sent_count = await maintenance.broadcast_maintenance_notification(
        bot,
        enabled=False,
    )
    assert sent_count == 2
    assert len(bot.sent) == 2
    chat_ids = {c.chat_id for c in bot.sent}
    assert chat_ids == {ADMIN_ID, STAFF_ID}
    for call in bot.sent:
        assert "Bot is back online" in call.text
        assert "Maintenance is complete" in call.text


@pytest.mark.asyncio
async def test_broadcast_maintenance_notification_off_custom(monkeypatch):
    """Broadcasting OFF with a custom resumed message uses the custom message verbatim."""
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [ADMIN_ID])
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    bot = FakeBot(me_id=BOT_ID)

    sent_count = await maintenance.broadcast_maintenance_notification(
        bot,
        enabled=False,
        custom_resumed_message="🟢 All services restored and operational!",
    )
    assert sent_count == 1
    assert "All services restored and operational!" in bot.sent[0].text


@pytest.mark.asyncio
async def test_service_resumed_uses_animated_emoji(monkeypatch):
    """When a custom animated emoji is configured for service_resumed, it upgrades 🟢."""
    from app.bot import emojis, strings
    emojis._slots_cache["service_resumed"].custom_emoji_id = "9876543210"
    try:
        text = strings.maintenance_broadcast_off_text()
        assert '<tg-emoji emoji-id="9876543210">🟢</tg-emoji>' in text
    finally:
        emojis._slots_cache["service_resumed"].custom_emoji_id = ""


@pytest.mark.asyncio
async def test_broadcast_maintenance_includes_group_chat_id(monkeypatch):
    """Broadcasting includes GROUP_CHAT_ID if configured."""
    monkeypatch.setattr(config, "ADMIN_USER_IDS", [ADMIN_ID])
    monkeypatch.setattr(config, "ALLOWED_USER_IDS", [])
    monkeypatch.setattr(config, "GROUP_CHAT_ID", -100123456789)
    bot = FakeBot(me_id=BOT_ID)

    sent = await maintenance.broadcast_maintenance_notification(bot, enabled=True)
    assert sent == 2
    chat_ids = {c.chat_id for c in bot.sent}
    assert chat_ids == {ADMIN_ID, -100123456789}


