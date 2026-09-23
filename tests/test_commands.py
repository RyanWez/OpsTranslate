from unittest.mock import AsyncMock, patch
import pytest
from aiogram import Bot
from app.bot.commands import register_bot_commands, load_bot_commands, save_bot_commands, DEFAULT_COMMANDS

@pytest.mark.asyncio
async def test_register_bot_commands_success():
    bot = AsyncMock(spec=Bot)
    bot.set_my_commands = AsyncMock(return_value=True)

    result = await register_bot_commands(bot)
    assert result is True
    bot.set_my_commands.assert_called_once()
    args, kwargs = bot.set_my_commands.call_args
    assert kwargs["commands"] == DEFAULT_COMMANDS

@pytest.mark.asyncio
async def test_register_bot_commands_failure():
    bot = AsyncMock(spec=Bot)
    bot.set_my_commands = AsyncMock(side_effect=Exception("Network error"))

    result = await register_bot_commands(bot)
    assert result is False

@pytest.mark.asyncio
async def test_load_bot_commands_fallback():
    with patch("app.store.db.is_configured", return_value=False):
        cmds = await load_bot_commands()
        assert cmds == DEFAULT_COMMANDS

@pytest.mark.asyncio
async def test_save_bot_commands_sync():
    bot = AsyncMock(spec=Bot)
    bot.set_my_commands = AsyncMock(return_value=True)
    custom = [{"command": "start", "description": "Custom Start"}]

    with patch("app.store.db.is_configured", return_value=False):
        saved = await save_bot_commands(custom, bot=bot)
        assert len(saved) == 1
        assert saved[0].command == "start"
        assert saved[0].description == "Custom Start"
        bot.set_my_commands.assert_called_once()
