import pytest
from unittest.mock import patch
from app.bot import emojis
from app.bot.emojis import (
    get_emoji,
    get_custom_emoji_id,
    load_emoji_config,
    save_emoji_config,
    get_all_slots,
    DEFAULT_SLOTS,
)

@pytest.fixture(autouse=True)
def protect_db_and_cache():
    import copy
    old_cache = {k: copy.deepcopy(v) for k, v in emojis._slots_cache.items()}
    with patch("app.store.db.is_configured", return_value=False):
        yield
    emojis._slots_cache = old_cache


@pytest.mark.asyncio
async def test_get_emoji_default_fallback():
    # Reset to defaults
    await save_emoji_config({})
    assert get_emoji("loading") == "⏳"
    assert get_emoji("header_globe") == "🌐"
    assert get_emoji("arrow") == "➡️"
    assert get_custom_emoji_id("loading") is None

@pytest.mark.asyncio
async def test_get_emoji_with_custom_id():
    await save_emoji_config({
        "loading": {"custom_emoji_id": "5368324170671202286", "fallback": "⏳"},
        "arrow": {"custom_emoji_id": "9988776655", "fallback": "➜"},
    })
    
    assert get_emoji("loading") == '<tg-emoji emoji-id="5368324170671202286">⏳</tg-emoji>'
    assert get_custom_emoji_id("loading") == "5368324170671202286"
    assert get_emoji("arrow") == '<tg-emoji emoji-id="9988776655">➜</tg-emoji>'

@pytest.mark.asyncio
async def test_get_all_slots_structure():
    slots = get_all_slots()
    keys = {s["key"] for s in slots}
    assert "loading" in keys
    assert "arrow" in keys
    assert "header_globe" in keys
    assert "copy_button" in keys
    assert "start_welcome" in keys


def test_welcome_text_personalized():
    from app.bot.strings import welcome_text
    
    # Generic
    msg = welcome_text()
    assert "Welcome to <b>OpsTranslate</b>!" in msg
    
    # Personalized
    msg2 = welcome_text(name="Zixuan", username="RyanWez")
    assert "Welcome, <b>Zixuan</b> (@RyanWez)!" in msg2
    assert "Auto Mode:" in msg2


@pytest.mark.asyncio
async def test_pure_custom_emoji_intercepted():
    from tests.fakes import FakeBot, FakeMessage, StubUserStore
    from tests.test_handlers import services_with
    from app.bot import handlers
    from aiogram.types import MessageEntity
    
    bot = FakeBot(me_id=999)
    services = services_with(bot, user_store=StubUserStore(allowed=True))
    
    # Send custom emoji
    msg = FakeMessage(message_id=101, text="👋")
    entity = MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="5368324170671202286")
    msg.entities = [entity]
    
    await handlers.on_text(msg, services, bot)
    assert len(msg.replies) == 1
    reply = msg.replies[0]
    assert "Custom Emoji Detected" in reply
    assert "5368324170671202286" in reply
    assert "Animated Emojis" in reply


@pytest.mark.asyncio
async def test_pure_standard_emoji_intercepted():
    from tests.fakes import FakeBot, FakeMessage, StubUserStore
    from tests.test_handlers import services_with
    from app.bot import handlers
    
    bot = FakeBot(me_id=999)
    services = services_with(bot, user_store=StubUserStore(allowed=True))
    
    # Send standard unicode emoji
    msg = FakeMessage(message_id=102, text="👋")
    msg.entities = []
    
    await handlers.on_text(msg, services, bot)
    assert len(msg.replies) == 1
    reply = msg.replies[0]
    assert "Standard Emoji" in reply
    assert "Telegram Premium" in reply

