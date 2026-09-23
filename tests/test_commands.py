from unittest.mock import AsyncMock
import pytest
from aiogram import Bot
from app.bot.commands import register_bot_commands, DEFAULT_COMMANDS

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
