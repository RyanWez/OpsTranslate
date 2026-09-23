"""Telegram Bot command registration (setMyCommands).

Registers standard commands into Telegram's menu button so staff and users
see the auto-complete command list without needing manual /setcommands setup
in @BotFather.

Supports dynamic configuration via the Admin Panel stored in the `settings`
table (key="bot_commands").
"""
from __future__ import annotations

import logging
from typing import Any
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

log = logging.getLogger("opstranslate.bot.commands")

# Default command list in English
DEFAULT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="🚀 Set up / change target language"),
    BotCommand(command="tr", description="🌐 Translate a replied-to message"),
    BotCommand(command="help", description="📖 How to use this bot"),
    BotCommand(command="status", description="📊 Bot and provider status"),
    BotCommand(command="report", description="🚩 Flag translation for review"),
    BotCommand(command="whoami", description="🆔 Check your Telegram user ID"),
]


async def load_bot_commands() -> list[BotCommand]:
    """Load dynamic commands from DB (settings table) or fallback to DEFAULT_COMMANDS."""
    from ..store import db as dbmod
    if dbmod.is_configured():
        try:
            from sqlalchemy import select
            from ..store.models import Setting

            async with dbmod.session() as sess:
                res = await sess.execute(select(Setting).where(Setting.key == "bot_commands"))
                setting = res.scalar_one_or_none()
                if setting and setting.value and isinstance(setting.value.get("commands"), list):
                    custom_cmds: list[BotCommand] = []
                    for c in setting.value["commands"]:
                        cmd_name = str(c.get("command", "")).strip().lstrip("/")
                        cmd_desc = str(c.get("description", "")).strip()
                        if cmd_name and cmd_desc:
                            custom_cmds.append(BotCommand(command=cmd_name, description=cmd_desc))
                    if custom_cmds:
                        return custom_cmds
        except Exception as exc:
            log.warning("failed to load custom bot commands from db: %s", exc)

    return list(DEFAULT_COMMANDS)


async def register_bot_commands(bot: Bot, commands: list[BotCommand] | None = None) -> bool:
    """Register menu commands with Telegram Bot API (setMyCommands)."""
    try:
        if commands is None:
            commands = await load_bot_commands()
        await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())
        log.info("Telegram bot menu commands registered successfully (%d commands)", len(commands))
        return True
    except Exception as exc:
        log.warning("failed to register bot menu commands: %s", exc)
        return False


async def save_bot_commands(
    commands: list[dict[str, str]], bot: Bot | None = None
) -> list[BotCommand]:
    """Save custom commands to database setting and sync to Telegram live."""
    from ..store import db as dbmod
    from ..store.models import Setting
    from sqlalchemy import select

    parsed: list[BotCommand] = []
    to_store: list[dict[str, str]] = []
    for c in commands:
        cmd_name = str(c.get("command", "")).strip().lstrip("/")
        cmd_desc = str(c.get("description", "")).strip()
        if cmd_name and cmd_desc:
            parsed.append(BotCommand(command=cmd_name, description=cmd_desc))
            to_store.append({"command": cmd_name, "description": cmd_desc})

    if not parsed:
        parsed = list(DEFAULT_COMMANDS)
        to_store = [{"command": c.command, "description": c.description} for c in DEFAULT_COMMANDS]

    if dbmod.is_configured():
        async with dbmod.session() as sess:
            res = await sess.execute(select(Setting).where(Setting.key == "bot_commands"))
            setting = res.scalar_one_or_none()
            if setting is None:
                setting = Setting(key="bot_commands", value={"commands": to_store})
                sess.add(setting)
            else:
                setting.value = {"commands": to_store}
            await sess.commit()

    if bot is not None:
        await register_bot_commands(bot, parsed)

    return parsed
