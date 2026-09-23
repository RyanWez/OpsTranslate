"""Telegram Bot command registration (setMyCommands).

Registers standard commands into Telegram's menu button so staff and users
see the auto-complete command list without needing manual /setcommands setup
in @BotFather.
"""
from __future__ import annotations

import logging
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

log = logging.getLogger("opstranslate.bot.commands")

DEFAULT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Set up / change target language"),
    BotCommand(command="tr", description="Translate a replied-to message"),
    BotCommand(command="help", description="How to use this bot"),
    BotCommand(command="status", description="Bot and provider status"),
    BotCommand(command="report", description="Flag the last translation for review"),
    BotCommand(command="whoami", description="Check your Telegram User ID"),
]


async def register_bot_commands(bot: Bot) -> bool:
    """Register menu commands with Telegram Bot API (setMyCommands)."""
    try:
        await bot.set_my_commands(commands=DEFAULT_COMMANDS, scope=BotCommandScopeDefault())
        log.info("Telegram bot menu commands registered successfully")
        return True
    except Exception as exc:
        log.warning("failed to register bot menu commands: %s", exc)
        return False
